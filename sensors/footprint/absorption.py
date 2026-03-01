import time
from typing import Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3
from sensors.footprint.matrix import LiveFootprintMatrix


class FootprintAbsorptionV3(SensorV3):
    """
    Footprint Absorption Sensor.

    Detects absorption: High volume traded at a price level but price fails to continue.

    Logic:
    - High Ask Volume at the High of the candle -> Absorption (Sellers absorbing Buyers) -> SHORT signal.
    - High Bid Volume at the Low of the candle -> Absorption (Buyers absorbing Sellers) -> LONG signal.
    """

    def __init__(
        self,
        min_volume_ratio: float = 2.0,
        pullback_ticks: int = 5,
        window_seconds: float = 30.0,
        tick_size: float = 0.1,
    ):
        super().__init__()
        self.min_volume_ratio = min_volume_ratio
        self.pullback_ticks = pullback_ticks
        self.matrix = LiveFootprintMatrix(window_seconds=window_seconds)
        self.market_profile = MarketProfile(tick_size=tick_size)

        self._last_signal_time = 0.0
        self._signal_cooldown = 2.0  # seconds between signals

    @property
    def name(self) -> str:
        return "FootprintAbsorption"

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        self.matrix.on_tick(tick_data)

        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("qty", 0))
        self.market_profile.add_trade(price, vol)

        now = time.time()
        if now - self._last_signal_time < self._signal_cooldown:
            return None

        profile = self.matrix.profile
        if not profile or len(profile) < 3:
            return None

        current_price = price

        # Find High and Low of the current sliding window
        prices = list(profile.keys())
        high = max(prices)
        low = min(prices)

        # Average volume per level for relative comparison
        total_vol = self.matrix.total_volume
        avg_vol_per_level = total_vol / len(profile)

        # We define a "pullback" as retreating from the extreme by a few price ticks
        # Simple heuristic: Use the average distance between levels
        prices.sort()
        avg_tick_size = (
            sum(prices[i + 1] - prices[i] for i in range(len(prices) - 1)) / len(prices) if len(prices) > 1 else 0.5
        )

        pullback_distance = avg_tick_size * self.pullback_ticks

        poc, vah, val = self.market_profile.calculate_value_area()

        signal = None

        # --- Scenario 1: Absorption at High (Bearish) ---
        # 1. High Volume at the top
        # 2. Price has pulled back from the High
        top_vol = profile.get(high, {"bid": 0.0, "ask": 0.0})
        if top_vol["ask"] > avg_vol_per_level * self.min_volume_ratio:
            if current_price <= high - pullback_distance:
                intensity = top_vol["ask"] / (avg_vol_per_level if avg_vol_per_level > 0 else 1.0)
                signal = {
                    "side": "SHORT",
                    "score": 0.9,
                    "metadata": {
                        "type": "Live_Absorption_High",
                        "vol": top_vol["ask"],
                        "fast_track": True,
                        "absorption_intensity": round(intensity, 2),
                        "poc": poc,
                        "vah": vah,
                        "val": val,
                    },
                }

        # --- Scenario 2: Absorption at Low (Bullish) ---
        # 1. High Volume at the bottom
        # 2. Price has bounced up from the Low
        low_vol = profile.get(low, {"bid": 0.0, "ask": 0.0})
        if not signal and low_vol["bid"] > avg_vol_per_level * self.min_volume_ratio:
            if current_price >= low + pullback_distance:
                intensity = low_vol["bid"] / (avg_vol_per_level if avg_vol_per_level > 0 else 1.0)
                signal = {
                    "side": "LONG",
                    "score": 0.9,
                    "metadata": {
                        "type": "Live_Absorption_Low",
                        "vol": low_vol["bid"],
                        "fast_track": True,
                        "absorption_intensity": round(intensity, 2),
                        "poc": poc,
                        "vah": vah,
                        "val": val,
                    },
                }

        if signal:
            self._last_signal_time = now
            return signal

        return None

    def on_orderbook(self, ob_data: dict) -> Optional[dict]:
        self.matrix.on_orderbook(ob_data)
        return None
