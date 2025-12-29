"""
ThreeBlackCrows Sensor (V3).
Logic: Three consecutive bearish candles with lower closes.
Classic bearish reversal/continuation pattern.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class ThreeBlackCrowsV3(SensorV3):
    @property
    def name(self) -> str:
        return "ThreeBlackCrows"

    def __init__(self):
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=4)  # 3 crows + 1 prior
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

        if len(buffer) < 4:
            return None

        crows = list(buffer)[-3:]  # Last 3 candles
        prior = list(buffer)[-4]

        # Prior candle should be bullish (reversal setup)
        if prior["close"] <= prior["open"]:
            return None

        # Check all 3 crows are bearish
        for c in crows:
            if c["close"] >= c["open"]:
                return None

        # Each close lower than previous
        for i in range(1, 3):
            if crows[i]["close"] >= crows[i - 1]["close"]:
                return None

        # Each open within previous body
        for i in range(1, 3):
            prev_open = crows[i - 1]["open"]
            prev_close = crows[i - 1]["close"]
            curr_open = crows[i]["open"]
            if not (prev_close < curr_open < prev_open):
                return None

        # Calculate strength based on body sizes
        bodies = [abs(c["close"] - c["open"]) for c in crows]
        avg_body = sum(bodies) / len(bodies)
        full_range = sum(c["high"] - c["low"] for c in crows) / 3
        body_ratio = avg_body / full_range if full_range > 0 else 0

        return {
            "side": "SHORT",
            "score": min(body_ratio + 0.3, 1.0),
            "timeframe": tf,
            "metadata": {"pattern": "three_black_crows"},
        }
