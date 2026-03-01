"""
Supertrend Sensor (V3).
Logic: Trend flip detection using ATR bands.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class SupertrendV3(SensorV3):
    @property
    def name(self) -> str:
        return "Supertrend"

    def __init__(self, atr_period=10, multiplier=3.0):
        self.atr_period = atr_period
        self.multiplier = multiplier
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.closes: Dict[str, deque] = {}
        self.last_supertrend: Dict[str, float] = {}
        self.last_direction: Dict[str, int] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.highs:
            self.highs[tf] = deque(maxlen=self.atr_period + 1)
            self.lows[tf] = deque(maxlen=self.atr_period + 1)
            self.closes[tf] = deque(maxlen=self.atr_period + 1)
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

        if len(closes) < self.atr_period:
            return None

        supertrend, direction = self._compute_supertrend(tf)
        if supertrend is None:
            return None

        last_dir = self.last_direction.get(tf)
        self.last_supertrend[tf] = supertrend
        self.last_direction[tf] = direction

        if last_dir is not None and direction != last_dir:
            side = "LONG" if direction == 1 else "SHORT"
            return {"side": side, "score": 1.0, "timeframe": tf, "metadata": {"supertrend": supertrend}}
        return None

    def _compute_supertrend(self, tf: str):
        highs, lows, closes = list(self.highs[tf]), list(self.lows[tf]), list(self.closes[tf])
        high, low, close = highs[-1], lows[-1], closes[-1]
        hl_avg = (high + low) / 2
        atr = self._compute_atr(tf)
        if atr == 0:
            return None, None

        upper_band = hl_avg + (self.multiplier * atr)
        lower_band = hl_avg - (self.multiplier * atr)

        last_st = self.last_supertrend.get(tf)
        last_dir = self.last_direction.get(tf)

        if last_st is None or last_dir is None:
            direction = 1 if close > upper_band else -1
            supertrend = lower_band if direction == 1 else upper_band
        elif last_dir == 1:
            if close < last_st:
                direction, supertrend = -1, upper_band
            else:
                direction, supertrend = 1, max(lower_band, last_st)
        else:
            if close > last_st:
                direction, supertrend = 1, lower_band
            else:
                direction, supertrend = -1, min(upper_band, last_st)

        return supertrend, direction

    def _compute_atr(self, tf: str):
        highs, lows, closes = list(self.highs[tf]), list(self.lows[tf]), list(self.closes[tf])
        if len(closes) < 2:
            return 0.0
        tr_values = [
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))
        ]
        return np.mean(tr_values[-self.atr_period :]) if tr_values else 0.0
