"""
ParabolicSAR Sensor (V3).
Logic: SAR trend reversal detection.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class ParabolicSARV3(SensorV3):
    @property
    def name(self) -> str:
        return "ParabolicSAR"

    def __init__(self, af_start=0.02, af_increment=0.02, af_max=0.20):
        self.af_start = af_start
        self.af_increment = af_increment
        self.af_max = af_max
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.sar: Dict[str, float] = {}
        self.ep: Dict[str, float] = {}
        self.af: Dict[str, float] = {}
        self.is_long: Dict[str, bool] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.highs:
            self.highs[tf] = deque(maxlen=100)
            self.lows[tf] = deque(maxlen=100)
            self.af[tf] = self.af_start
            self.is_long[tf] = True
        return self.highs[tf], self.lows[tf]

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
        highs, lows = self._get_buffers(tf)
        high, low = candle["high"], candle["low"]
        highs.append(high)
        lows.append(low)

        if tf not in self.sar:
            if len(highs) >= 2:
                self._initialize_sar(tf)
            return None

        return self._update_sar(tf, high, low)

    def _initialize_sar(self, tf: str):
        highs, lows = self.highs[tf], self.lows[tf]
        if highs[-1] > highs[-2]:
            self.is_long[tf] = True
            self.sar[tf] = min(lows[-2], lows[-1])
            self.ep[tf] = max(highs[-2], highs[-1])
        else:
            self.is_long[tf] = False
            self.sar[tf] = max(highs[-2], highs[-1])
            self.ep[tf] = min(lows[-2], lows[-1])
        self.af[tf] = self.af_start

    def _update_sar(self, tf: str, high, low):
        prev_sar = self.sar[tf]
        self.sar[tf] = prev_sar + self.af[tf] * (self.ep[tf] - prev_sar)

        if self.is_long[tf]:
            self.sar[tf] = min(self.sar[tf], self.lows[tf][-1] if self.lows[tf] else low)
            if low < self.sar[tf]:
                self.is_long[tf] = False
                self.sar[tf] = self.ep[tf]
                self.ep[tf] = low
                self.af[tf] = self.af_start
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"sar": self.sar[tf]}}
            if high > self.ep[tf]:
                self.ep[tf] = high
                self.af[tf] = min(self.af[tf] + self.af_increment, self.af_max)
        else:
            self.sar[tf] = max(self.sar[tf], self.highs[tf][-1] if self.highs[tf] else high)
            if high > self.sar[tf]:
                self.is_long[tf] = True
                self.sar[tf] = self.ep[tf]
                self.ep[tf] = high
                self.af[tf] = self.af_start
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"sar": self.sar[tf]}}
            if low < self.ep[tf]:
                self.ep[tf] = low
                self.af[tf] = min(self.af[tf] + self.af_increment, self.af_max)
        return None
