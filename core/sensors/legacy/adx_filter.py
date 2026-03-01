"""
ADXFilter Sensor (V3).
Logic: ADX trend strength filter with directional signals.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class ADXFilterV3(SensorV3):
    @property
    def name(self) -> str:
        return "ADXFilter"

    def __init__(self, period=14, adx_threshold=25.0, use_directional=True):
        self.period = period
        self.adx_threshold = adx_threshold
        self.use_directional = use_directional
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.closes: Dict[str, deque] = {}
        self.dx_values: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.highs:
            self.highs[tf] = deque(maxlen=self.period + 1)
            self.lows[tf] = deque(maxlen=self.period + 1)
            self.closes[tf] = deque(maxlen=self.period + 1)
            self.dx_values[tf] = deque(maxlen=self.period)
        return self.highs[tf], self.lows[tf], self.closes[tf]

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
        highs, lows, closes = self._get_buffers(tf)
        highs.append(candle["high"])
        lows.append(candle["low"])
        closes.append(candle["close"])

        di_plus, di_minus = self._compute_di(tf)
        if di_plus is None:
            return None

        adx = self._compute_adx(tf, di_plus, di_minus)
        if adx is None or adx < self.adx_threshold or not self.use_directional:
            return None

        side = "LONG" if di_plus > di_minus else "SHORT"
        return {"side": side, "score": 1.0, "timeframe": tf, "metadata": {"adx": adx}}

    def _compute_di(self, tf: str):
        highs, lows, closes = list(self.highs[tf]), list(self.lows[tf]), list(self.closes[tf])
        if len(highs) < 2:
            return None, None

        plus_dm, minus_dm, tr_list = [], [], []
        for i in range(1, len(highs)):
            up = highs[i] - highs[i - 1]
            down = lows[i - 1] - lows[i]
            plus_dm.append(up if up > down and up > 0 else 0)
            minus_dm.append(down if down > up and down > 0 else 0)
            tr_list.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

        if len(tr_list) < self.period:
            return None, None

        smoothed_tr = np.mean(tr_list[-self.period :])
        if smoothed_tr == 0:
            return None, None

        return (np.mean(plus_dm[-self.period :]) / smoothed_tr) * 100, (
            np.mean(minus_dm[-self.period :]) / smoothed_tr
        ) * 100

    def _compute_adx(self, tf: str, di_plus, di_minus):
        di_sum = di_plus + di_minus
        if di_sum == 0:
            return 0.0
        dx = (abs(di_plus - di_minus) / di_sum) * 100
        self.dx_values[tf].append(dx)
        return np.mean(self.dx_values[tf]) if len(self.dx_values[tf]) >= self.period else None
