"""
ThreeWhiteSoldiers Sensor (V3).
Logic: Three consecutive bullish candles with higher closes.
Classic bullish reversal/continuation pattern.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class ThreeWhiteSoldiersV3(SensorV3):
    @property
    def name(self) -> str:
        return "ThreeWhiteSoldiers"

    def __init__(self):
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=4)  # 3 soldiers + 1 prior
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

        soldiers = list(buffer)[-3:]  # Last 3 candles
        prior = list(buffer)[-4]

        # Prior candle should be bearish (reversal setup)
        if prior["close"] >= prior["open"]:
            return None

        # Check all 3 soldiers are bullish
        for c in soldiers:
            if c["close"] <= c["open"]:
                return None

        # Each close higher than previous
        for i in range(1, 3):
            if soldiers[i]["close"] <= soldiers[i - 1]["close"]:
                return None

        # Each open within previous body
        for i in range(1, 3):
            prev_open = soldiers[i - 1]["open"]
            prev_close = soldiers[i - 1]["close"]
            curr_open = soldiers[i]["open"]
            if not (prev_open < curr_open < prev_close):
                return None

        # Calculate strength based on body sizes
        bodies = [abs(c["close"] - c["open"]) for c in soldiers]
        avg_body = sum(bodies) / len(bodies)
        full_range = sum(c["high"] - c["low"] for c in soldiers) / 3
        body_ratio = avg_body / full_range if full_range > 0 else 0

        return {
            "side": "LONG",
            "score": min(body_ratio + 0.3, 1.0),
            "timeframe": tf,
            "metadata": {"pattern": "three_white_soldiers"},
        }
