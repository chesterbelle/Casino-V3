"""
DecelerationCandles Sensor (V3).
Tier 3: Good.
Logic: Sequence of shrinking candles indicating exhaustion.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class DecelerationCandlesV3(SensorV3):
    @property
    def name(self) -> str:
        return "DecelerationCandles"

    def __init__(self, sequence_length=3):
        self.sequence_length = sequence_length
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.sequence_length)
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

        if len(buffer) < self.sequence_length:
            return None

        bodies = [abs(c["close"] - c["open"]) for c in buffer]
        directions = [1 if c["close"] > c["open"] else -1 for c in buffer]

        # All same direction
        if not all(d == directions[0] for d in directions):
            return None

        # Bodies shrinking
        if not all(bodies[i + 1] < bodies[i] for i in range(len(bodies) - 1)):
            return None

        side = "SHORT" if directions[0] == 1 else "LONG"
        return {"side": side, "score": 1.0, "timeframe": tf, "metadata": {"pattern": "deceleration"}}
