"""
ThreeBar Sensor (V3).
Logic: Three bar reversal pattern detection.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class ThreeBarV3(SensorV3):
    @property
    def name(self) -> str:
        return "ThreeBar"

    def __init__(self, range_decrease=0.7, close_threshold=0.4):
        self.range_decrease = range_decrease
        self.close_threshold = close_threshold
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=5)
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

        if len(buffer) < 3:
            return None

        first, second, third = buffer[-3], buffer[-2], buffer[-1]
        first_range = first["high"] - first["low"]
        second_range = second["high"] - second["low"]

        if first_range == 0:
            return None

        if second_range / first_range > self.range_decrease:
            return None

        # Bullish: Down-Small-Up
        if first["close"] < first["open"] and third["close"] > third["open"]:
            if third["close"] > first["open"] - (first_range * self.close_threshold):
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "bullish_three_bar"}}

        # Bearish: Up-Small-Down
        if first["close"] > first["open"] and third["close"] < third["open"]:
            if third["close"] < first["open"] + (first_range * self.close_threshold):
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "bearish_three_bar"}}

        return None
