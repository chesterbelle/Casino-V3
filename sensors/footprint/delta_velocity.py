"""
Delta Velocity Lead Indicator - Phase 1600 (CSO Enhancement)

Tracks the velocity (rate of change) of Cumulative Volume Delta (CVD)
relative to Price velocity.

Key Signals:
1. Momentum Surge: High Delta velocity + High Price velocity in same direction.
2. Absorption Exhaustion: High Delta velocity + Decelerating Price velocity.
3. Hidden Accumulation: Low Price velocity + High Delta velocity.
"""

import time
from collections import deque
from typing import Optional

from sensors.base import SensorV3


class DeltaVelocitySensorV3(SensorV3):
    def __init__(self, window_seconds: float = 10.0, snapshot_hz: float = 2.0):
        super().__init__()
        self.window_seconds = window_seconds
        self.snapshot_interval = 1.0 / snapshot_hz

        # History of (timestamp, price, cvd)
        self.history = deque(maxlen=int(window_seconds * snapshot_hz) + 1)
        self.current_cvd = 0.0
        self._last_snapshot_ts = 0.0

    @property
    def name(self) -> str:
        return "DeltaVelocity"

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("qty", 0))
        is_buyer_maker = tick_data.get("is_buyer_maker", False)

        # Update current CVD
        if is_buyer_maker:
            self.current_cvd -= vol
        else:
            self.current_cvd += vol

        now = time.time()

        # Take periodic snapshots
        if now - self._last_snapshot_ts >= self.snapshot_interval:
            self.history.append((now, price, self.current_cvd))
            self._last_snapshot_ts = now

        # Analysis
        if len(self.history) < 5:
            return None

        # Calculate velocities over 2s and 5s windows
        v2s = self._calculate_velocity(2.0)
        v5s = self._calculate_velocity(5.0)

        if not v2s or not v5s:
            return None

        # Determine lead signals
        price_vel = v2s["price_vel"]
        delta_vel = v2s["delta_vel"]

        signal_type = None
        multiplier = 1.0

        # Thresholds for 'Surge' (needs calibration, starting with relative units)
        # Using Z-score or Vol-ratio adjusted thresholds would be better,
        # but let's start with a simplified volatility-relative check.

        # 1. Momentum Surge (Aligned)
        if abs(delta_vel) > abs(v5s["delta_vel"]) * 1.5:
            if (delta_vel > 0 and price_vel > 0) or (delta_vel < 0 and price_vel < 0):
                signal_type = "Momentum_Surge"
                multiplier = 1.3
            # 2. Absorption Exhaustion (Divergent velocity)
            elif abs(price_vel) < abs(v5s["price_vel"]) * 0.5:
                signal_type = "Exhaustion_Divergence"
                multiplier = 0.7  # Reduce size when price decelerates against delta

        if signal_type:
            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalDeltaVelocity",
                    "subtype": signal_type,
                    "delta_velocity": round(delta_vel, 2),
                    "price_velocity": round(price_vel, 6),
                    "sizing_multiplier": multiplier,
                },
            }

        return None

    def _calculate_velocity(self, lookback_secs: float) -> Optional[dict]:
        """Calculates (ΔValue / ΔTime) over the lookback window."""
        if len(self.history) < 2:
            return None

        now = self.history[-1][0]
        cutoff = now - lookback_secs

        # Find the snapshot closest to cutoff
        start_node = None
        for h in self.history:
            if h[0] >= cutoff:
                start_node = h
                break

        if not start_node or start_node == self.history[-1]:
            return None

        dt = now - start_node[0]
        if dt <= 0:
            return None

        dp = self.history[-1][1] - start_node[1]
        dc = self.history[-1][2] - start_node[2]

        return {"price_vel": dp / dt, "delta_vel": dc / dt, "dt": dt}

    def on_orderbook(self, ob_data: dict) -> Optional[dict]:
        return None
