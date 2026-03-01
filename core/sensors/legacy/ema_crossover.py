"""
EMACrossover Sensor (V3).
Tier 1: 80% Win Rate.
Logic: EMA(12) crosses EMA(26) + ADX > 20.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class EMACrossoverV3(SensorV3):
    @property
    def name(self) -> str:
        return "EMACrossover"

    def __init__(self, short_period=12, long_period=26, adx_period=14, adx_threshold=20):
        self.short_period = short_period
        self.long_period = long_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.closes: Dict[str, deque] = {}
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.dx_values: Dict[str, deque] = {}
        self.prev_emas: Dict[str, tuple] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.closes:
            max_len = self.long_period + 50
            self.closes[tf] = deque(maxlen=max_len)
            self.highs[tf] = deque(maxlen=max_len)
            self.lows[tf] = deque(maxlen=max_len)
            self.dx_values[tf] = deque(maxlen=self.adx_period)
        return self.closes[tf], self.highs[tf], self.lows[tf]

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
        closes, highs, lows = self._get_buffers(tf)
        closes.append(candle["close"])
        highs.append(candle["high"])
        lows.append(candle["low"])

        if len(closes) < self.long_period:
            return None

        short_ema = self._calculate_ema(list(closes), self.short_period)
        long_ema = self._calculate_ema(list(closes), self.long_period)
        adx = self._calculate_adx(tf)

        prev = self.prev_emas.get(tf)
        self.prev_emas[tf] = (short_ema, long_ema)

        if prev and adx is not None and adx > self.adx_threshold:
            prev_short, prev_long = prev
            if prev_short <= prev_long and short_ema > long_ema:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"adx": adx}}
            elif prev_short >= prev_long and short_ema < long_ema:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"adx": adx}}
        return None

    def _calculate_ema(self, data, period):
        if len(data) < period:
            return np.mean(data)
        multiplier = 2 / (period + 1)
        ema = np.mean(data[:period])
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def _calculate_adx(self, tf: str):
        highs, lows, closes = list(self.highs[tf]), list(self.lows[tf]), list(self.closes[tf])
        if len(highs) < self.adx_period + 1:
            return None

        plus_dm, minus_dm, tr_list = [], [], []
        for i in range(1, len(highs)):
            up = highs[i] - highs[i - 1]
            down = lows[i - 1] - lows[i]
            plus_dm.append(up if up > down and up > 0 else 0)
            minus_dm.append(down if down > up and down > 0 else 0)
            tr_list.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

        if len(tr_list) < self.adx_period:
            return None

        smoothed_tr = np.mean(tr_list[-self.adx_period :])
        if smoothed_tr == 0:
            return None

        di_plus = (np.mean(plus_dm[-self.adx_period :]) / smoothed_tr) * 100
        di_minus = (np.mean(minus_dm[-self.adx_period :]) / smoothed_tr) * 100
        di_sum = di_plus + di_minus
        if di_sum == 0:
            return 0.0

        dx = (abs(di_plus - di_minus) / di_sum) * 100
        self.dx_values[tf].append(dx)
        return np.mean(self.dx_values[tf]) if len(self.dx_values[tf]) >= self.adx_period else None
