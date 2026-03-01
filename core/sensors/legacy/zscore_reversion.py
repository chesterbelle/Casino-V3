"""
ZScoreReversion Sensor (V3).
Logic: Z-Score statistical mean reversion.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class ZScoreReversionV3(SensorV3):
    @property
    def name(self) -> str:
        return "ZScoreReversion"

    def __init__(self, period=20, entry_threshold=2.0):
        self.period = period
        self.entry_threshold = entry_threshold
        self.closes: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=self.period)
        return self.closes[tf]

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
        buffer.append(candle["close"])

        if len(buffer) < self.period:
            return None

        arr = np.array(buffer)
        mean, std = np.mean(arr), np.std(arr)
        if std == 0:
            return None

        zscore = (buffer[-1] - mean) / std

        if zscore < -self.entry_threshold:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"zscore": zscore}}
        if zscore > self.entry_threshold:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"zscore": zscore}}
        return None
