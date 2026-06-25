import logging
import math
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

from .market_profile import MarketProfile
from .symbol_manager import symbol_mapper
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
        self.pressure_state: Dict[str, dict] = {}

        # Phase A2: Session-aware structural levels (overwritten by SessionValueArea events)
        self._session_structural: Dict[str, dict] = {}  # symbol -> {poc, vah, val}

        # Phase B1: Current liquidity window per symbol (for dynamic VA thresholds)
        self.current_window: Dict[str, str] = {}  # symbol -> window_name

        # Phase B3: Spread tracking for spread sanity gate
        self.spread_state: Dict[str, dict] = {}  # symbol -> {current, avg_5m, history}

        # Phase 2100: V2 Regime data from MarketRegimeSensor (3-layer anticipatory)
        self._regime_v2: Dict[str, dict] = {}  # symbol -> full V2 regime dict

        # Phase C1: Liquidity Heatmap (Location Alpha)
        self.liquidity_walls: Dict[str, Dict[float, float]] = defaultdict(dict)  # symbol -> {price: volume}
        self.l2_imbalance: Dict[str, float] = defaultdict(lambda: 1.0)  # symbol -> L2 Ratio (Bid/Ask)
        # Phase C2: Wall persistence counter for spoofing detection
        self._wall_age: Dict[str, Dict[float, int]] = defaultdict(
            lambda: defaultdict(int)
        )  # symbol -> {price: age_in_snapshots}

        # Volatility Layer (Phase 1300: Adaptive Thresholds)
        self.attr_short_window = 10
        self.attr_long_window = 100
        self.ranges_short: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.attr_short_window))
        self.ranges_long: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.attr_long_window))
        self.atrs: Dict[str, Dict[str, float]] = defaultdict(lambda: {"short": 0.0, "long": 0.0})

        # v8.3: Running sums O(1) for spread & ATR
        self._spread_running_sum: Dict[str, float] = {}
        self._range_short_running_sum: Dict[str, float] = {}
        self._range_long_running_sum: Dict[str, float] = {}

        # v8.3: Rolling window of VWAP residuals O(1) for std
        self._vwap_residuals: Dict[str, dict] = defaultdict(lambda: {"history": deque(maxlen=500), "sum_sq": 0.0})

        # Phase D1: Rolling VWAP & Z-Bands (Statistical Location)
        self.vwap_window_secs = 120 * 60  # 120 minutes
        self.vwap_history: Dict[str, deque] = defaultdict(deque)
        self.vwap_state: Dict[str, dict] = defaultdict(lambda: {"vwap": 0.0, "std": 0.0})
        self.vwap_accumulators: Dict[str, dict] = defaultdict(lambda: {"pv": 0.0, "v": 0.0})

        # Gravity Layer (System Global)
        self.btc_delta = 0.0
        self.btc_trend = "NEUTRAL"

        logger.info("🏛️ ContextRegistry (Zero-Lag Mirror) initialized.")

    def set_pressure_state(self, symbol: str, state):
        self.pressure_state[symbol] = state

    def get_pressure_state(self, symbol: str):
        return self.pressure_state.get(symbol)

    def on_tick(self, symbol: str, price: float, volume: float, side: str, timestamp: Optional[float] = None):
        """Update structural and pulse layers synchronously."""
        now = timestamp or time.time()
        if symbol not in self.profiles:
            sym_tick_size = tick_registry.get(symbol)
            self.profiles[symbol] = MarketProfile(tick_size=sym_tick_size, rolling_window=28800)
            self.tick_stats[symbol] = {"speed": 0.0, "last_ts": now, "count": 0}

        # 1. Update Market Profile with rolling window (handles drift internally)
        self.profiles[symbol].add_trade(price, volume, timestamp=now)

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

        Args:
            symbol: Trading symbol
            poc: Point of Control
            vah: Value Area High
            val: Value Area Low
            va_integrity: VA integrity score from session sensor
        """
        self._session_structural[symbol] = {"poc": poc, "vah": vah, "val": val, "va_integrity": va_integrity}

    def reset_profile(self, symbol: str):
        """Phase 1150: Resets MarketProfile for a symbol to prevent cumulative drift.
        Should be called at the start of each new trading session / dataset.
        """
        profile = self.profiles.get(symbol)
        if profile:
            profile.reset()

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
        Prefers rolling-window profile (current regime) over session-scoped (accumulated).
        """
        # Primary: rolling window profile evaluates current regime (last 8h)
        profile = self.profiles.get(symbol)
        if profile and profile.total_volume > 0:
            return profile.calculate_va_integrity()

        # Fallback: session-scoped integrity (may accumulate full session)
        session = self._session_structural.get(symbol)
        if session and session.get("va_integrity", 0) > 0:
            return session["va_integrity"]

        return 0.0

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

    def get_regime_v2(self, symbol: str) -> dict:
        """Phase 2100: Returns full V2 regime data."""
        return self._regime_v2.get(symbol, {"regime": "BALANCE", "reversion_allowed": True})

    def _norm_key(self, symbol: str) -> str:
        """Normalize symbol to a canonical key for dict lookups."""
        return symbol_mapper.normalize(symbol)

    def set_micro_state(self, symbol: str, cvd: float, skewness: float, z_score: float):
        """Update real-time microstructure state."""
        key = self._norm_key(symbol)
        self.micro_state[key] = {
            "cvd": cvd,
            "skewness": skewness,
            "z_score": z_score,
            "last_update": time.time(),
        }

    def get_micro_state(self, symbol: str) -> Tuple[float, float, float]:
        """Returns (cvd, skewness, z_score) for the symbol."""
        key = self._norm_key(symbol)
        state = self.micro_state.get(key)
        if not state:
            return 0.0, 0.5, 0.0
        return state.get("cvd", 0.0), state.get("skewness", 0.5), state.get("z_score", 0.0)

    def update_spread(self, symbol: str, spread: float):
        """Phase B3: Track spread for spread sanity gate. O(1) running sum."""
        if symbol not in self.spread_state:
            self.spread_state[symbol] = {"current": 0.0, "avg_5m": 0.0, "history": deque(maxlen=300)}
            self._spread_running_sum[symbol] = 0.0

        state = self.spread_state[symbol]
        state["current"] = spread

        history = state["history"]
        if len(history) >= history.maxlen:
            self._spread_running_sum[symbol] -= history[0]

        history.append(spread)
        self._spread_running_sum[symbol] += spread
        state["avg_5m"] = self._spread_running_sum[symbol] / len(history)

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
        """Update ATR buffers from candle data. O(1) running sum."""
        candle_range = high - low
        if candle_range <= 0:
            return

        short_history = self.ranges_short[symbol]
        long_history = self.ranges_long[symbol]

        if symbol not in self._range_short_running_sum:
            self._range_short_running_sum[symbol] = 0.0
            self._range_long_running_sum[symbol] = 0.0

        if len(short_history) >= short_history.maxlen:
            self._range_short_running_sum[symbol] -= short_history[0]
        if len(long_history) >= long_history.maxlen:
            self._range_long_running_sum[symbol] -= long_history[0]

        short_history.append(candle_range)
        long_history.append(candle_range)
        self._range_short_running_sum[symbol] += candle_range
        self._range_long_running_sum[symbol] += candle_range

        self.atrs[symbol]["short"] = self._range_short_running_sum[symbol] / len(short_history)
        self.atrs[symbol]["long"] = self._range_long_running_sum[symbol] / len(long_history)

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

    def update_liquidity(self, symbol: str, bids: list, asks: list):
        """
        Phase C1: Update liquidity walls from OrderBook snapshot.
        Only keeps significant 'walls' to minimize memory and query time.
        """
        key = self._norm_key(symbol)
        new_walls = {}

        # We only care about the top 20 levels for each side for HFT Location Alpha
        # And only if they are significantly larger than the average depth

        all_levels = bids[:20] + asks[:20]
        if not all_levels:
            return

        # Single pass: calculate L2 ratio, average volume, and detect walls
        bid_vol = 0.0
        ask_vol = 0.0
        total_vol = 0.0

        if bids and asks:
            try:
                mid_price = float(bids[0][0])
                for p, v in bids:
                    pf = float(p)
                    vf = float(v)
                    if pf >= mid_price * 0.998:
                        bid_vol += vf
                for p, v in asks:
                    pf = float(p)
                    vf = float(v)
                    if pf <= mid_price * 1.002:
                        ask_vol += vf
                self.l2_imbalance[key] = max(bid_vol, 0.01) / max(ask_vol, 0.01)
            except Exception:
                pass

        # Single pass: compute total volume and detect walls
        new_walls = {}
        for price_str, vol_str in all_levels:
            vol = float(vol_str)
            total_vol += vol

        avg_vol = total_vol / len(all_levels) if all_levels else 0.0

        wall_age_map = self._wall_age[key]
        for price_str, vol_str in all_levels:
            price = float(price_str)
            vol = float(vol_str)
            if vol > avg_vol * 1.5:  # 1.5x average is a 'wall'
                # Track wall persistence across snapshots (spoofing filter)
                wall_age_map[price] = wall_age_map.get(price, 0) + 1
                if wall_age_map[price] >= 3:  # Only count walls persisting >= 3 snapshots
                    new_walls[price] = vol

        # Purge stale wall ages (no longer present in this snapshot)
        current_prices = {float(p) for p, _ in all_levels}
        stale = [p for p in wall_age_map if p not in current_prices]
        for p in stale:
            del wall_age_map[p]

        self.liquidity_walls[key] = new_walls

    def get_liquidity_score(self, symbol: str, target_price: float, side: str, tolerance_pct: float = 0.0005) -> float:
        """
        Phase C1: Returns a score (0.0 to 1.0) based on liquidity support.
        - target_price: The price we want to validate (e.g. VAL or Entry).
        - side: LONG (look for bids below/at) or SHORT (look for asks above/at).
        - tolerance_pct: Price window to search for walls.
        """
        key = self._norm_key(symbol)
        walls = self.liquidity_walls.get(key, {})
        if not walls:
            return 0.5  # Neutral if no data

        # Find walls within tolerance
        upper = target_price * (1 + tolerance_pct)
        lower = target_price * (1 - tolerance_pct)

        relevant_walls = [vol for price, vol in walls.items() if lower <= price <= upper]

        if not relevant_walls:
            return 0.2  # 'Air' - No liquidity support

        # If we find walls, the score is 1.0 (Supported)
        return 1.0

    def get_l2_ratio(self, symbol: str, side: str) -> float:
        """Returns the L2 Depth Ratio. > 1.0 means wall is supporting the trade."""
        key = self._norm_key(symbol)
        ratio = self.l2_imbalance[key]
        if side == "LONG":
            return ratio
        else:
            return 1.0 / ratio if ratio > 0 else 1.0

    def update_vwap(self, symbol: str, price: float, volume: float, timestamp: float = None):
        """
        Phase D1: Update Rolling VWAP state (High Performance).
        Uses running sums + online residual std for O(1) at all times.
        """
        now = timestamp or time.time()
        key = self._norm_key(symbol)

        # Feed the Silicon Eye for real-time tick inference
        tick_registry.observe_price(symbol, price)

        history = self.vwap_history[key]
        acc = self.vwap_accumulators[key]

        # 1. Add new point to history and accumulator
        pv = price * volume
        history.append((now, price, volume, pv))
        acc["pv"] += pv
        acc["v"] += volume

        # 2. Evict expired points (O(1) amortized with popleft)
        cutoff = now - self.vwap_window_secs
        while history and history[0][0] < cutoff:
            _, _, old_v, old_pv = history.popleft()
            acc["pv"] -= old_pv
            acc["v"] -= old_v

        # 3. Update State (VWAP)
        if acc["v"] > 0:
            vwap = acc["pv"] / acc["v"]

            # 4. Standard Deviation — O(1) exact rolling residual std
            # v8.3 fix: Store residual (price - vwap) at insertion time, so eviction
            # subtracts exactly the value that was added — no approximation needed.
            res = self._vwap_residuals[key]
            residual = price - vwap
            res["history"].append(residual)
            res["sum_sq"] += residual * residual
            if len(res["history"]) > res["history"].maxlen:
                old_residual = res["history"].popleft()
                res["sum_sq"] -= old_residual * old_residual

            n = len(res["history"])
            std = math.sqrt(res["sum_sq"] / n) if n > 1 else 0.0
            self.vwap_state[key] = {"vwap": vwap, "std": std}

    def get_vwap_zscore(self, symbol: str, current_price: float) -> float:
        """
        Returns the Z-Score of the current price relative to the Rolling VWAP.
        Z = (Price - VWAP) / Std
        """
        key = self._norm_key(symbol)
        state = self.vwap_state.get(key)
        if not state or state["std"] == 0:
            return 0.0

        return (current_price - state["vwap"]) / state["std"]
