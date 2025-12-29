"""
VCPPattern Sensor (V3).
Tier 3: Good.
Logic: Volatility Contraction Pattern.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class VCPPatternV3(SensorV3):
    @property
    def name(self) -> str:
        return "VCPPattern"

    def __init__(self, contractions=3):
        self.contractions = contractions
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.contractions)
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

        if len(buffer) < self.contractions:
            return None

        ranges = [c["high"] - c["low"] for c in buffer]
        if not all(ranges[i + 1] < ranges[i] for i in range(len(ranges) - 1)):
            return None

        if buffer[-1]["volume"] >= buffer[0]["volume"]:
            return None

        side = "LONG" if buffer[-1]["close"] > buffer[0]["close"] else "SHORT"
        return {"side": side, "score": 1.0, "timeframe": tf, "metadata": {"pattern": "vcp"}}
