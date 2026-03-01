"""
TweezerPattern Sensor (V3).
Logic: Tweezer tops and bottoms detection.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class TweezerPatternV3(SensorV3):
    @property
    def name(self) -> str:
        return "TweezerPattern"

    def __init__(self, max_diff_pct=0.0005, min_body_pct=0.002):
        self.max_diff_pct = max_diff_pct
        self.min_body_pct = min_body_pct
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

        if len(buffer) < 2:
            return None

        first, second = buffer[-2], buffer[-1]
        avg_price = (first["high"] + first["low"] + second["high"] + second["low"]) / 4

        # Tweezer Bottom
        low_diff_pct = abs(first["low"] - second["low"]) / avg_price
        if low_diff_pct < self.max_diff_pct:
            if first["close"] < first["open"] and second["close"] > second["open"]:
                if abs(second["close"] - second["open"]) / avg_price > self.min_body_pct:
                    return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "tweezer_bottom"}}

        # Tweezer Top
        high_diff_pct = abs(first["high"] - second["high"]) / avg_price
        if high_diff_pct < self.max_diff_pct:
            if first["close"] > first["open"] and second["close"] < second["open"]:
                if abs(second["close"] - second["open"]) / avg_price > self.min_body_pct:
                    return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "tweezer_top"}}

        return None
