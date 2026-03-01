"""
KeltnerReversion Sensor (V3).
Logic: Price extends beyond Keltner Channels (mean reversion).

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class KeltnerReversionV3(SensorV3):
    @property
    def name(self) -> str:
        return "KeltnerReversion"

    def __init__(self, window=20, multiplier=2.0):
        self.window = window
        self.multiplier = multiplier
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.closes: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.highs:
            self.highs[tf] = deque(maxlen=self.window)
            self.lows[tf] = deque(maxlen=self.window)
            self.closes[tf] = deque(maxlen=self.window)
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

        if len(closes) < self.window:
            return None

        typical = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
        ema = self._ema(typical)
        atr = self._atr(tf)
        upper, lower = ema + self.multiplier * atr, ema - self.multiplier * atr
        close = closes[-1]

        if close < lower:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"atr": atr}}
        if close > upper:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"atr": atr}}
        return None

    def _ema(self, values):
        alpha = 2 / (self.window + 1)
        ema = values[0]
        for v in values[1:]:
            ema = alpha * v + (1 - alpha) * ema
        return ema

    def _atr(self, tf: str):
        highs, lows, closes = list(self.highs[tf]), list(self.lows[tf]), list(self.closes[tf])
        trs = [
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))
        ]
        return np.mean(trs) if trs else 0.0
