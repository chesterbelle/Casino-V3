"""
LongTail Sensor (V3).
Logic: Detects long-tailed distribution patterns.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class LongTailV3(SensorV3):
    @property
    def name(self) -> str:
        return "LongTail"

    def __init__(self, lookback=5, tail_factor=3.0, min_tail_pct=0.003):
        self.lookback = lookback
        self.tail_factor = tail_factor
        self.min_tail_pct = min_tail_pct
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback + 5)
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

        open_p, high, low, close = candle["open"], candle["high"], candle["low"], candle["close"]
        body_top, body_bottom = max(open_p, close), min(open_p, close)
        upper_tail, lower_tail = high - body_top, body_bottom - low
        avg_price = (high + low) / 2 or 1

        # Calculate average tails from prev candles
        prev = list(buffer)[:-1]
        prev_lower = [min(c["open"], c["close"]) - c["low"] for c in prev]
        prev_upper = [c["high"] - max(c["open"], c["close"]) for c in prev]
        avg_lower, avg_upper = np.mean(prev_lower) if prev_lower else 0, np.mean(prev_upper) if prev_upper else 0

        # Long lower tail (bullish)
        if lower_tail / avg_price > self.min_tail_pct and avg_lower > 0 and lower_tail > avg_lower * self.tail_factor:
            if close > open_p:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "long_lower_tail"}}

        # Long upper tail (bearish)
        if upper_tail / avg_price > self.min_tail_pct and avg_upper > 0 and upper_tail > avg_upper * self.tail_factor:
            if close < open_p:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "long_upper_tail"}}

        return None
