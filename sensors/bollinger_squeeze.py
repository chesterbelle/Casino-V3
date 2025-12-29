"""
BollingerSqueeze Sensor (V3).
Logic: Low volatility squeeze followed by breakout with volume.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class BollingerSqueezeV3(SensorV3):
    @property
    def name(self) -> str:
        return "BollingerSqueeze"

    def __init__(self, period=20, std_dev=2.0, squeeze_threshold=0.02, volume_factor=1.2):
        self.period = period
        self.std_dev = std_dev
        self.squeeze_threshold = squeeze_threshold
        self.volume_factor = volume_factor
        self.closes: Dict[str, deque] = {}
        self.volumes: Dict[str, deque] = {}
        self.in_squeeze: Dict[str, bool] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=self.period)
            self.volumes[tf] = deque(maxlen=self.period)
            self.in_squeeze[tf] = False
        return self.closes[tf], self.volumes[tf]

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
        closes, volumes = self._get_buffers(tf)
        closes.append(candle["close"])
        volumes.append(candle["volume"])

        if len(closes) < self.period:
            return None

        closes_arr = np.array(closes)
        middle = np.mean(closes_arr)
        std = np.std(closes_arr)
        upper = middle + (self.std_dev * std)
        lower = middle - (self.std_dev * std)
        bbw = (upper - lower) / middle if middle > 0 else 0.0

        if bbw < self.squeeze_threshold:
            self.in_squeeze[tf] = True
            return None

        if not self.in_squeeze.get(tf, False):
            return None

        avg_volume = np.mean(list(volumes)[:-1])
        if volumes[-1] < avg_volume * self.volume_factor:
            return None

        close = candle["close"]
        if close > upper:
            self.in_squeeze[tf] = False
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"bbw": bbw}}
        elif close < lower:
            self.in_squeeze[tf] = False
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"bbw": bbw}}

        return None
