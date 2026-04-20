import logging
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

from .market_profile import MarketProfile
from .tick_registry import tick_registry

logger = logging.getLogger(__name__)


class ContextRegistry:
    """
    Synchronous Context Registry (Mirror Pattern).

    Provides 0-latency access to 7 layers of context:
    1. Structural: VAH, VAL, POC, IB
    2. Regime: TREND, RANGE, NORMAL
    3. Flow: OTF, Cumulative Delta
    4. Micro: Clusters, Unfinished Business
    5. Pulse: Tick Speed, Real-Time Vol
    6. Gravity: BTC Correlation (Proxy)
    7. Dynamics: IB Extensions, Gap Fill
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ContextRegistry, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.profiles: Dict[str, MarketProfile] = {}
        self.regimes: Dict[str, str] = {}  # symbol -> regime (TREND, RANGE, etc.)
        self.otf: Dict[str, str] = {}  # symbol -> OTF (BULL_OTF, BEAR_OTF, NEUTRAL)
        self.tick_stats: Dict[str, dict] = {}  # symbol -> {speed, last_ts, count}
        self.micro_state: Dict[str, dict] = {}  # symbol -> {cvd, skewness, z_score, last_update}
        self.ib_levels: Dict[str, dict] = {}  # symbol -> {high, low}  Phase 700: IB levels for proximity gate
        self.active_trades: Dict[str, bool] = defaultdict(bool)  # symbol -> in_trade (Phase 974)

        # Phase A2: Session-aware structural levels (overwritten by SessionValueArea events)
        self._session_structural: Dict[str, dict] = {}  # symbol -> {poc, vah, val}

        # Phase B1: Current liquidity window per symbol (for dynamic VA thresholds)
        self.current_window: Dict[str, str] = {}  # symbol -> window_name

        # Phase B3: Spread tracking for spread sanity gate
        self.spread_state: Dict[str, dict] = {}  # symbol -> {current, avg_5m, history}

        # Phase 2100: V2 Regime data from MarketRegimeSensor (3-layer anticipatory)
        self._regime_v2: Dict[str, dict] = {}  # symbol -> full V2 regime dict

        # Volatility Layer (Phase 1300: Adaptive Thresholds)
        self.attr_short_window = 10
        self.attr_long_window = 100
        self.ranges_short: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.attr_short_window))
        self.ranges_long: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.attr_long_window))
        self.atrs: Dict[str, Dict[str, float]] = defaultdict(lambda: {"short": 0.0, "long": 0.0})

        # Gravity Layer (System Global)
        self.btc_delta = 0.0
        self.btc_trend = "NEUTRAL"

        logger.info("🏛️ ContextRegistry (Zero-Lag Mirror) initialized.")

    def on_tick(self, symbol: str, price: float, volume: float, side: str, timestamp: Optional[float] = None):
        """Update structural and pulse layers synchronously."""
        now = timestamp or time.time()
        if symbol not in self.profiles:
            sym_tick_size = tick_registry.get(symbol)
            self.profiles[symbol] = MarketProfile(tick_size=sym_tick_size)
            self.tick_stats[symbol] = {"speed": 0.0, "last_ts": now, "count": 0}

        # 1. Update Market Profile
        self.profiles[symbol].add_trade(price, volume)

        # 2. Update Pulse (Tick Speed)
        stats = self.tick_stats[symbol]
        stats["count"] += 1
        elapsed = now - stats["last_ts"]
        if elapsed >= 1.0:  # Update speed every second
            stats["speed"] = stats["count"] / elapsed
            stats["count"] = 0
            stats["last_ts"] = now

        # 3. Update Gravity if symbol is BTC
        if "BTC" in symbol:
            delta = volume if side == "buy" else -volume
            self.btc_delta += delta

    def get_structural(self, symbol: str) -> Tuple[float, float, float]:
        """Returns (POC, VAH, VAL) for the symbol.
        Phase A2: Prefers session-aware levels when available,
        falling back to the tick-accumulated global profile.
        """
        # Prefer session-aware levels (updated by SessionValueArea events)
        session = self._session_structural.get(symbol)
        if session and session.get("poc", 0) > 0:
            return session["poc"], session["vah"], session["val"]

        # Fallback to global tick-accumulated profile
        profile = self.profiles.get(symbol)
        if not profile:
            return 0.0, 0.0, 0.0
        return profile.calculate_value_area()

    def update_structural_from_session(
        self, symbol: str, poc: float, vah: float, val: float, va_integrity: float = 0.0
    ):
        """Phase A2: Update structural levels from SessionValueArea sensor.
        This ensures the SetupEngine guardians use the same per-window
        levels as the session sensor, avoiding stale cumulative averages.
        Phase 2000: Also caches session-scoped VA integrity.
        """
        if poc > 0 and vah > 0 and val > 0:
            self._session_structural[symbol] = {
                "poc": poc,
                "vah": vah,
                "val": val,
                "va_integrity": va_integrity,
            }

    def set_ib(self, symbol: str, ib_high: float, ib_low: float):
        """Phase 700: Store IB boundaries for level proximity checks."""
        self.ib_levels[symbol] = {"high": ib_high, "low": ib_low}

    def get_ib(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Phase 700: Returns (ib_high, ib_low) or (None, None)."""
        ib = self.ib_levels.get(symbol)
        if ib:
            return ib["high"], ib["low"]
        return None, None

    def is_structural_ready(self, symbol: str) -> bool:
        """Phase 1800: Returns True if structural levels (POC, VAH, VAL) are loaded.
        Used by SetupEngine to ensure the bot isn't "blind" before firing signals.
        """
        poc, vah, val = self.get_structural(symbol)
        return poc > 0 and vah > 0 and val > 0

    def get_regime(self, symbol: str) -> str:
        """Returns (TREND, RANGE, NORMAL)."""
        return self.regimes.get(symbol, "NORMAL")

    def get_poc_migration(self, symbol: str, lookback_ticks: int = 300) -> float:
        """
        Phase 1150: Returns the % change of POC over the lookback period.
        Used to detect 'Value Migration' (Price Acceptance) vs Rejection.
        """
        profile = self.profiles.get(symbol)
        if not profile or len(profile.poc_history) < 2:
            return 0.0

        history = list(profile.poc_history)
        current_poc = history[-1]
        start_idx = max(0, len(history) - lookback_ticks)
        start_poc = history[start_idx]

        if start_poc == 0:
            return 0.0

        return (current_poc - start_poc) / start_poc

    def get_va_integrity(self, symbol: str) -> float:
        """Phase 1150: Returns the VA Integrity Score.
        Phase 2000: Prefers session-scoped integrity from the SessionValueArea sensor.
        Falls back to the global cumulative profile only on cold start.
        """
        # Prefer session-scoped integrity (fresh per liquidity window)
        session = self._session_structural.get(symbol)
        if session and session.get("va_integrity", 0) > 0:
            return session["va_integrity"]

        # Fallback: global cumulative profile (stale but better than nothing)
        profile = self.profiles.get(symbol)
        if not profile:
            return 0.0
        return profile.calculate_va_integrity()

    def set_in_trade(self, symbol: str, in_trade: bool):
        """Phase 974: Set active trade status for a symbol."""
        self.active_trades[symbol] = in_trade
        logger.debug(f"⚖️  [CONTEXT] {symbol} trade status: {'IN_TRADE' if in_trade else 'FLAT'}")

    def is_in_trade(self, symbol: str) -> bool:
        """Phase 974: Check if a symbol is currently in an active trade."""
        return self.active_trades.get(symbol, False)

    def get_pulse(self, symbol: str) -> dict:
        """Returns real-time speed and volatility metrics."""
        return self.tick_stats.get(symbol, {"speed": 0.0})

    def get_gravity(self) -> dict:
        """Returns global market health (BTC Proxy)."""
        return {"btc_delta": self.btc_delta, "btc_trend": self.btc_trend}

    def set_regime(self, symbol: str, regime: str):
        self.regimes[symbol] = regime

    def set_otf(self, symbol: str, otf: str):
        self.otf[symbol] = otf

    def set_regime_v2(self, symbol: str, regime_data: dict):
        """Phase 2100: Store full V2 regime data from MarketRegimeSensor."""
        self._regime_v2[symbol] = regime_data

    def set_micro_state(self, symbol: str, cvd: float, skewness: float, z_score: float):
        """Update real-time microstructure state."""
        self.micro_state[symbol] = {
            "cvd": cvd,
            "skewness": skewness,
            "z_score": z_score,
            "last_update": time.time(),
        }

    def get_micro_state(self, symbol: str) -> Tuple[float, float, float]:
        """Returns (cvd, skewness, z_score) for the symbol."""
        state = self.micro_state.get(symbol)
        if not state:
            return 0.0, 0.5, 0.0
        return state.get("cvd", 0.0), state.get("skewness", 0.5), state.get("z_score", 0.0)

    def update_spread(self, symbol: str, spread: float):
        """Phase B3: Track spread for spread sanity gate."""
        if symbol not in self.spread_state:
            self.spread_state[symbol] = {"current": 0.0, "avg_5m": 0.0, "history": deque(maxlen=300)}

        state = self.spread_state[symbol]
        state["current"] = spread
        state["history"].append(spread)
        if len(state["history"]) > 0:
            state["avg_5m"] = sum(state["history"]) / len(state["history"])

    def get_flow_inertia(self, symbol: str, side: str, profit_pct: float = 0.0) -> float:
        """
        Phase 700: Simplified flow inertia — LAZY mode only.
        Returns:
            > 1.0 (Lazy/Momentum Support): Increase trailing buffer to let winners run.
            = 1.0 (Neutral): Default trailing distance.
        Paranoid mode removed: structural SL handles adverse flow.
        """
        state = self.micro_state.get(symbol)
        if not state:
            return 1.0

        cvd = state["cvd"]
        skew = state["skewness"]
        z = state["z_score"]

        inertia = 1.0

        if side == "LONG":
            # LAZY Conditions: Price and Flow moving together
            if cvd > 500 and skew > 0.55 and z < 4.0:
                inertia = 1.7
        else:  # SHORT
            # LAZY Conditions
            if cvd < -500 and skew < 0.45 and z > -4.0:
                inertia = 1.7

        return inertia

    def on_candle(self, symbol: str, high: float, low: float):
        """Update ATR buffers from candle data."""
        candle_range = high - low
        if candle_range <= 0:
            return

        self.ranges_short[symbol].append(candle_range)
        self.ranges_long[symbol].append(candle_range)

        # Update cached averages
        self.atrs[symbol]["short"] = sum(self.ranges_short[symbol]) / len(self.ranges_short[symbol])
        self.atrs[symbol]["long"] = sum(self.ranges_long[symbol]) / len(self.ranges_long[symbol])

    def get_volatility_ratio(self, symbol: str) -> float:
        """
        Returns ATR_Short / ATR_Long.
        Used to adapt thresholds during volatility expansion.
        Returns 1.0 (neutral) if insufficient data.
        """
        atr_data = self.atrs.get(symbol)
        if not atr_data or atr_data["long"] == 0:
            return 1.0

        ratio = atr_data["short"] / atr_data["long"]
        # Clamp to reasonable range [0.5, 2.0]
        return max(0.5, min(2.0, ratio))
