import time
from typing import Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3
from sensors.footprint.matrix import LiveFootprintMatrix


class CumulativeDeltaSensorV3(SensorV3):
    """
    Cumulative Volume Delta (CVD) Sensor.

    Tracks the ongoing battle between aggressive buyers and sellers over a sliding window.
    Identifies 'Delta Divergence' (e.g., price makes a new high, but CVD drops, signaling exhaustion).
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        divergence_threshold: float = 2.0,  # Ratio of price move vs delta move needed for signal
        tick_size: float = 0.1,
    ):
        super().__init__()
        self.window_seconds = window_seconds
        self.divergence_threshold = divergence_threshold
        self.matrix = LiveFootprintMatrix(window_seconds=window_seconds)
        self.market_profile = MarketProfile(tick_size=tick_size)

        # CVD Tracking
        self.current_cvd = 0.0
        self.cvd_history = []  # List of (timestamp, price, cvd)

        # Highs/Lows for divergence checks
        self.session_high = float("-inf")
        self.session_low = float("inf")
        self.cvd_at_high = 0.0
        self.cvd_at_low = 0.0

        self._last_signal_time = 0.0
        self._signal_cooldown = 5.0  # seconds

    @property
    def name(self) -> str:
        return "CumulativeDelta"

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        self.matrix.on_tick(tick_data)

        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("qty", 0))
        is_buyer_maker = tick_data.get("is_buyer_maker", False)

        self.market_profile.add_trade(price, vol)

        now = time.time()

        # Update CVD: If buyer is maker, it means a seller was the aggressive taker (hit the bid)
        if is_buyer_maker:
            self.current_cvd -= vol
        else:
            self.current_cvd += vol

        # Maintain history for divergence calculation (cleanup old entries)
        self.cvd_history.append((now, price, self.current_cvd))
        self.cvd_history = [x for x in self.cvd_history if now - x[0] <= self.window_seconds]

        # Update session extremes
        if price > self.session_high:
            self.session_high = price
            self.cvd_at_high = self.current_cvd
        if price < self.session_low:
            self.session_low = price
            self.cvd_at_low = self.current_cvd

        # Check coercion timeline
        if now - self._last_signal_time < self._signal_cooldown or len(self.cvd_history) < 10:
            return None

        # Check for Divergence
        # 1. Bearish Divergence: Price near session high, but CVD is dropping significantly lower than when we made that high
        if price >= self.session_high * 0.9999:  # Very close to high
            # Is current CVD significantly lower than the CVD when we hit the absolute high?
            if self.current_cvd < self.cvd_at_high - (
                self.matrix.total_volume * 0.1
            ):  # delta gap > 10% of total volume
                intensity = abs(self.current_cvd - self.cvd_at_high) / (
                    self.matrix.total_volume if self.matrix.total_volume > 0 else 1.0
                )
                poc, vah, val = self.market_profile.calculate_value_area()
                self._last_signal_time = now
                return {
                    "side": "SHORT",
                    "score": 0.85,
                    "metadata": {
                        "type": "Live_Delta_Bearish_Divergence",
                        "fast_track": True,
                        "cvd": round(self.current_cvd, 2),
                        "intensity": round(intensity, 2),
                        "poc": poc,
                        "vah": vah,
                        "val": val,
                    },
                }

        # 2. Bullish Divergence: Price near session low, but CVD is rising significantly higher than when we made that low
        if price <= self.session_low * 1.0001:  # Very close to low
            if self.current_cvd > self.cvd_at_low + (self.matrix.total_volume * 0.1):
                intensity = abs(self.current_cvd - self.cvd_at_low) / (
                    self.matrix.total_volume if self.matrix.total_volume > 0 else 1.0
                )
                poc, vah, val = self.market_profile.calculate_value_area()
                self._last_signal_time = now
                return {
                    "side": "LONG",
                    "score": 0.85,
                    "metadata": {
                        "type": "Live_Delta_Bullish_Divergence",
                        "fast_track": True,
                        "cvd": round(self.current_cvd, 2),
                        "intensity": round(intensity, 2),
                        "poc": poc,
                        "vah": vah,
                        "val": val,
                    },
                }

        return None

    def on_orderbook(self, ob_data: dict) -> Optional[dict]:
        self.matrix.on_orderbook(ob_data)
        return None
