"""
MorningStar Sensor (V3).
Logic: Morning Star / Evening Star 3-candle reversal.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class MorningStarV3(SensorV3):
    @property
    def name(self) -> str:
        return "MorningStar"

    def __init__(self, min_large_body_pct=0.004, max_star_body_pct=0.002):
        self.min_large_body_pct = min_large_body_pct
        self.max_star_body_pct = max_star_body_pct
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=10)
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

        c1, c2, c3 = buffer[-3], buffer[-2], buffer[-1]
        c1_body = abs(c1["close"] - c1["open"])
        c2_body = abs(c2["close"] - c2["open"])
        c3_body = abs(c3["close"] - c3["open"])

        price = c3["close"]
        c1_pct = c1_body / price
        c2_pct = c2_body / price
        c3_pct = c3_body / price

        if c1_pct < self.min_large_body_pct or c2_pct > self.max_star_body_pct or c3_pct < self.min_large_body_pct:
            return None

        # Morning Star
        if c1["close"] < c1["open"] and c3["close"] > c3["open"]:
            if c3["close"] > (c1["open"] + c1["close"]) / 2:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "morning_star"}}

        # Evening Star
        elif c1["close"] > c1["open"] and c3["close"] < c3["open"]:
            if c3["close"] < (c1["open"] + c1["close"]) / 2:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "evening_star"}}

        return None
