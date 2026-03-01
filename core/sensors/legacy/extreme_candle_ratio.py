"""
ExtremeCandleRatio Sensor (V3).
Tier 2: Excellent.
Logic: Candle body larger than historical percentile.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class ExtremeCandleRatioV3(SensorV3):
    @property
    def name(self) -> str:
        return "ExtremeCandleRatio"

    def __init__(self, lookback=30, percentile=0.95):
        self.lookback = lookback
        self.percentile = percentile
        self.bodies: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.bodies:
            self.bodies[tf] = deque(maxlen=self.lookback + 1)
        return self.bodies[tf]

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
        body = abs(candle["close"] - candle["open"])

        if len(buffer) < self.lookback:
            buffer.append(body)
            return None

        threshold = np.percentile(buffer, self.percentile * 100)
        buffer.append(body)

        if body > threshold:
            side = "LONG" if candle["close"] > candle["open"] else "SHORT"
            return {
                "side": side,
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"ratio": body / threshold if threshold else 0},
            }
        return None
