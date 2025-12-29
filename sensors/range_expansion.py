"""
RangeExpansion Sensor (V3).
Logic: Current bar's range is significantly larger than average.
Indicates momentum/volatility breakout.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class RangeExpansionV3(SensorV3):
    @property
    def name(self) -> str:
        return "RangeExpansion"

    def __init__(self, lookback=14, expansion_threshold=2.0):
        self.lookback = lookback
        self.expansion_threshold = expansion_threshold
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

        expansion_ratio = current_range / avg_range

        if expansion_ratio < self.expansion_threshold:
            return None

        # Signal in direction of the expansion bar
        if candle["close"] > candle["open"]:
            side = "LONG"
        else:
            side = "SHORT"

        # Score based on expansion magnitude
        score = min(expansion_ratio / 4.0, 1.0)

        return {
            "side": side,
            "score": score,
            "timeframe": tf,
            "metadata": {
                "pattern": "range_expansion",
                "expansion_ratio": expansion_ratio,
            },
        }
