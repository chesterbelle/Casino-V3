"""
ConsecutiveCandles Sensor (V3).
Logic: N consecutive candles closing in the same direction.
Signals potential exhaustion/mean reversion opportunity.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class ConsecutiveCandlesV3(SensorV3):
    @property
    def name(self) -> str:
        return "ConsecutiveCandles"

    def __init__(self, min_consecutive=4):
        self.min_consecutive = min_consecutive
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.min_consecutive + 1)
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

        if len(buffer) < self.min_consecutive:
            return None

        # Check direction of each candle
        directions = []
        for c in buffer:
            if c["close"] > c["open"]:
                directions.append(1)  # Bullish
            elif c["close"] < c["open"]:
                directions.append(-1)  # Bearish
            else:
                directions.append(0)  # Doji

        # Count consecutive same direction from the end
        consecutive_count = 1
        last_dir = directions[-1]

        if last_dir == 0:
            return None  # Last candle is doji

        for i in range(len(directions) - 2, -1, -1):
            if directions[i] == last_dir:
                consecutive_count += 1
            else:
                break

        if consecutive_count < self.min_consecutive:
            return None

        # After N bullish candles, expect SHORT (mean reversion)
        # After N bearish candles, expect LONG
        side = "SHORT" if last_dir == 1 else "LONG"

        # Score based on how many consecutive
        score = min(consecutive_count / 6.0, 1.0)

        return {
            "side": side,
            "score": score,
            "timeframe": tf,
            "metadata": {
                "pattern": "consecutive",
                "count": consecutive_count,
                "direction": "bullish" if last_dir == 1 else "bearish",
            },
        }
