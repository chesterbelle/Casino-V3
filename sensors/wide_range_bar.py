"""
WideRangeBar Sensor (V3).
Logic: Current bar has an unusually wide range compared to recent bars.
Indicates strong momentum or trend change.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class WideRangeBarV3(SensorV3):
    @property
    def name(self) -> str:
        return "WideRangeBar"

    def __init__(self, lookback=10, threshold_multiplier=1.5):
        self.lookback = lookback
        self.threshold_multiplier = threshold_multiplier
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback)
        return self.candles[tf]

    def calculate(self, context: dict) -> List[dict]:
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
        buffer = self._get_buffer(tf)
        buffer.append(candle)

        if len(buffer) < self.lookback:
            return None

        # Calculate ranges
        ranges = [c["high"] - c["low"] for c in buffer]
        current_range = ranges[-1]
        avg_range = sum(ranges[:-1]) / (len(ranges) - 1)

        if avg_range == 0:
            return None

        # Check if current range is significantly above average
        if current_range < avg_range * self.threshold_multiplier:
            return None

        # Signal in direction of the wide bar
        if candle["close"] > candle["open"]:
            side = "LONG"
        elif candle["close"] < candle["open"]:
            side = "SHORT"
        else:
            return None  # Doji wide bar - skip

        range_ratio = current_range / avg_range
        score = min(range_ratio / 3.0, 1.0)

        return {
            "side": side,
            "score": score,
            "timeframe": tf,
            "metadata": {
                "pattern": "wide_range_bar",
                "range_ratio": range_ratio,
            },
        }
