"""
PinBarReversal Sensor (V3).
Tier 1: 76% Win Rate.
Logic: Wick > 2x Body + Close in top/bottom 30%.

Multi-TF: Monitors multiple timeframes with independent signals.
"""

import logging
from typing import List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class PinBarReversalV3(SensorV3):
    @property
    def name(self) -> str:
        return "PinBarReversal"

    def __init__(self, wick_ratio=2.0, position_threshold=0.3):
        self.wick_ratio = wick_ratio
        self.position_threshold = position_threshold

    def calculate(self, context: dict) -> List[dict]:
        """Calculate signals for all monitored timeframes."""
        signals = []

        for tf in self.timeframes:
            candle = context.get(tf)
            if candle is None:
                continue

            signal = self._calculate_for_tf(tf, candle)
            if signal:
                signals.append(signal)

        return signals if signals else None

    def _calculate_for_tf(self, tf: str, candle: dict) -> Optional[dict]:
        """Calculate PinBar signal for a single timeframe."""
        open_p = candle["open"]
        close_p = candle["close"]
        high_p = candle["high"]
        low_p = candle["low"]

        body_size = abs(close_p - open_p)
        total_range = high_p - low_p

        if total_range == 0:
            return None

        # Calculate Wicks
        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p

        # Bearish Pin Bar (Long Upper Wick)
        if upper_wick > (body_size * self.wick_ratio):
            close_pos = (close_p - low_p) / total_range
            if close_pos < self.position_threshold:
                return {
                    "side": "SHORT",
                    "score": 1.0,
                    "timeframe": tf,
                    "metadata": {"wick_ratio": upper_wick / body_size if body_size else 99},
                }

        # Bullish Pin Bar (Long Lower Wick)
        elif lower_wick > (body_size * self.wick_ratio):
            close_pos = (close_p - low_p) / total_range
            if close_pos > (1 - self.position_threshold):
                return {
                    "side": "LONG",
                    "score": 1.0,
                    "timeframe": tf,
                    "metadata": {"wick_ratio": lower_wick / body_size if body_size else 99},
                }

        return None
