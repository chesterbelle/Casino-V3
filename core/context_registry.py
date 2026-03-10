import logging
import time
from typing import Dict, Tuple

from core.market_profile import MarketProfile

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

    def __init__(self, tick_size: float = 0.1):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.tick_size = tick_size
        self.profiles: Dict[str, MarketProfile] = {}
        self.regimes: Dict[str, str] = {}  # symbol -> regime (TREND, RANGE, etc.)
        self.otf: Dict[str, str] = {}  # symbol -> OTF (BULL_OTF, BEAR_OTF, NEUTRAL)
        self.tick_stats: Dict[str, dict] = {}  # symbol -> {speed, last_ts, count}

        # Gravity Layer (System Global)
        self.btc_delta = 0.0
        self.btc_trend = "NEUTRAL"

        logger.info("🏛️ ContextRegistry (Zero-Lag Mirror) initialized.")

    def on_tick(self, symbol: str, price: float, volume: float, side: str):
        """Update structural and pulse layers synchronously."""
        if symbol not in self.profiles:
            self.profiles[symbol] = MarketProfile(tick_size=self.tick_size)
            self.tick_stats[symbol] = {"speed": 0.0, "last_ts": time.time(), "count": 0}

        # 1. Update Market Profile
        self.profiles[symbol].add_trade(price, volume)

        # 2. Update Pulse (Tick Speed)
        now = time.time()
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
        """Returns (POC, VAH, VAL) for the symbol."""
        profile = self.profiles.get(symbol)
        if not profile:
            return 0.0, 0.0, 0.0
        return profile.calculate_value_area()

    def get_regime(self, symbol: str) -> str:
        """Returns the current market regime."""
        return self.regimes.get(symbol, "NORMAL")

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
