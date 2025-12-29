"""
VolumeImbalance Sensor (V3).
Logic: Buying/selling pressure imbalance detection.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class VolumeImbalanceV3(SensorV3):
    @property
    def name(self) -> str:
        return "VolumeImbalance"

    def __init__(self, volume_period=20, imbalance_ratio=3.0):
        self.volume_period = volume_period
        self.imbalance_ratio = imbalance_ratio
        self.volumes: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.volumes:
            self.volumes[tf] = deque(maxlen=self.volume_period)
        return self.volumes[tf]

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
        vol = candle["volume"]
        buffer.append(vol)

        if len(buffer) < self.volume_period:
            return None

        avg_vol = np.mean(buffer)
        if vol < avg_vol:
            return None

        close, high, low, open_p = candle["close"], candle["high"], candle["low"], candle["open"]
        buying = close - low or 0.000001
        selling = high - close or 0.000001

        if buying > selling * self.imbalance_ratio and close > open_p:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"vol_ratio": vol / avg_vol}}
        if selling > buying * self.imbalance_ratio and close < open_p:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"vol_ratio": vol / avg_vol}}
        return None
