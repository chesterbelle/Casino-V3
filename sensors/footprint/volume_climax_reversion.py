"""
TacticalVolumeClimaxReversion Sensor - LTA V5
Detects volume climax at VA edges without price extension.

More robust than VelocityReversion (fixed 60s timing) because it uses
volume exhaustion + price failure as confirmation, not arbitrary time windows.

Inspired by Wyckoff climactic action and DOM false break patterns.
"""

import time
from collections import deque
from typing import Any, Dict, Optional

import numpy as np

from sensors.base import SensorV3


class TacticalVolumeClimaxReversion(SensorV3):
    """
    Detects volume climax at VA edges where price fails to extend.

    Pattern:
    1. Extreme volume spike (>3x average) at VAH or VAL
    2. Price fails to extend beyond the edge (closes within 30% of range)
    3. Delta reverses in the same candle (buying exhaustion → selling, or vice versa)

    This indicates institutional rejection of the level - they absorbed the
    aggressive flow but won't push price further.

    More reliable than timing-based approaches because it measures actual
    market behavior (volume + price action + delta) rather than arbitrary timeframes.
    """

    def __init__(self):
        super().__init__()
        self.timeframe = "1m"

        # Volume tracking for average calculation
        self.volume_history = deque(maxlen=20)

        # Delta tracking for reversal detection
        self.delta_history = deque(maxlen=5)

        # Cooldown
        self.last_signal_ts = 0.0
        self.signal_cooldown = 30.0  # 30 seconds between signals

        # Configuration (Made more strict to reduce false signals)
        self.volume_spike_threshold = 4.0  # Increased from 3.0 to 4.0x average
        self.price_extension_max = 0.20  # Reduced from 0.30 to 0.20 (stricter failure)
        self.delta_reversal_threshold = 0.0  # Delta must flip sign
        self.min_volume_history = 15  # Need more history before signaling

    @property
    def name(self) -> str:
        return "TacticalVolumeClimaxReversion"

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        """Main calculation on each 1m candle."""
        candle = context.get(self.timeframe)
        if not candle:
            return None

        # Extract candle data
        high = float(candle.get("high", 0))
        low = float(candle.get("low", 0))
        close = float(candle.get("close", 0))
        volume = float(candle.get("volume", 0))
        timestamp = float(candle.get("timestamp", time.time()))

        # Get structural levels from context
        poc = float(candle.get("poc", 0))
        vah = float(candle.get("vah", 0))
        val = float(candle.get("val", 0))

        if high <= 0 or low <= 0 or volume <= 0:
            return None

        if poc <= 0 or vah <= 0 or val <= 0:
            return None  # Need structural levels

        # Update volume history
        self.volume_history.append(volume)

        # Need minimum history (increased for more stable average)
        if len(self.volume_history) < self.min_volume_history:
            return None

        # Check cooldown
        if timestamp - self.last_signal_ts < self.signal_cooldown:
            return None

        # Calculate average volume
        avg_volume = np.mean(self.volume_history)

        # 1. Check for volume spike
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        if volume_ratio < self.volume_spike_threshold:
            return None  # Not a climax

        # 2. Check if at VA edge
        price_range = high - low
        proximity_threshold = 0.0025  # 0.25% proximity to edge

        at_vah = abs(high - vah) / vah < proximity_threshold
        at_val = abs(low - val) / val < proximity_threshold

        if not (at_vah or at_val):
            return None  # Not at an edge

        # 3. Check for failed price extension
        # For bullish climax at VAL: close should be in lower 30% of range
        # For bearish climax at VAH: close should be in upper 30% of range

        if at_val:
            # Bullish climax - buying exhaustion
            # Close should fail to extend (be in lower portion of range)
            close_position = (close - low) / price_range if price_range > 0 else 0.5

            if close_position > self.price_extension_max:
                return None  # Price extended too much, not a failed climax

            # 4. Check for delta reversal (optional but preferred)
            delta = candle.get("delta", 0.0)
            cvd = candle.get("cvd", 0.0)

            # For bullish climax, we want to see delta turn negative (selling pressure)
            # STRICT: Delta must be negative (not just neutral) to confirm exhaustion
            if delta >= 0:
                return None  # Still bullish or neutral flow, not exhaustion

            # Signal: LONG reversion from VAL
            self.last_signal_ts = timestamp
            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalVolumeClimaxReversion",
                    "direction": "LONG",
                    "pattern": "Volume_Climax_VAL",
                    "price": close,
                    "volume": volume,
                    "volume_ratio": round(volume_ratio, 2),
                    "avg_volume": round(avg_volume, 2),
                    "close_position_pct": round(close_position * 100, 1),
                    "delta": delta,
                    "cvd": cvd,
                    "val": val,
                    "vah": vah,
                    "poc": poc,
                    "high": high,
                    "low": low,
                    "close": close,
                },
            }

        if at_vah:
            # Bearish climax - selling exhaustion
            # Close should fail to extend down (be in upper portion of range)
            close_position = (high - close) / price_range if price_range > 0 else 0.5

            if close_position > self.price_extension_max:
                return None  # Price extended too much down, not a failed climax

            # Check for delta reversal
            delta = candle.get("delta", 0.0)
            cvd = candle.get("cvd", 0.0)

            # For bearish climax, we want to see delta turn positive (buying pressure)
            # STRICT: Delta must be positive (not just neutral) to confirm exhaustion
            if delta <= 0:
                return None  # Still bearish or neutral flow, not exhaustion

            # Signal: SHORT reversion from VAH
            self.last_signal_ts = timestamp
            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalVolumeClimaxReversion",
                    "direction": "SHORT",
                    "pattern": "Volume_Climax_VAH",
                    "price": close,
                    "volume": volume,
                    "volume_ratio": round(volume_ratio, 2),
                    "avg_volume": round(avg_volume, 2),
                    "close_position_pct": round(close_position * 100, 1),
                    "delta": delta,
                    "cvd": cvd,
                    "val": val,
                    "vah": vah,
                    "poc": poc,
                    "high": high,
                    "low": low,
                    "close": close,
                },
            }

        return None
