"""
KeltnerBreakout Sensor (V3).
Logic: Detects breakouts from Keltner Channel.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class KeltnerBreakoutV3(SensorV3):
    @property
    def name(self) -> str:
        return "KeltnerBreakout"

    def __init__(self, ema_period=20, atr_period=10, atr_multiplier=2.0):
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.closes: Dict[str, deque] = {}
        self.trs: Dict[str, deque] = {}
        self.candles: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        max_len = max(self.ema_period, self.atr_period) + 10
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=max_len)
            self.trs[tf] = deque(maxlen=max_len)
            self.candles[tf] = deque(maxlen=max_len)
        return self.closes[tf], self.trs[tf], self.candles[tf]

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
        closes, trs, candles = self._get_buffers(tf)
        closes.append(candle["close"])
        candles.append(candle)

        # Calculate True Range
        tr = self._calculate_tr(tf, candle)
        trs.append(tr)

        if len(closes) < self.ema_period or len(trs) < self.atr_period:
            return None

        ema = self._calculate_ema(list(closes), self.ema_period)
        atr = np.mean(list(trs)[-self.atr_period :])
        upper = ema + (self.atr_multiplier * atr)
        lower = ema - (self.atr_multiplier * atr)

        close = candle["close"]
        open_p = candle["open"]

        if close > upper and close > open_p:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"upper": upper, "atr": atr}}
        if close < lower and close < open_p:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"lower": lower, "atr": atr}}
        return None

    def _calculate_tr(self, tf: str, candle):
        candles = self.candles.get(tf, [])
        if len(candles) < 2:
            return candle["high"] - candle["low"]
        prev_close = candles[-2]["close"]
        return max(candle["high"] - candle["low"], abs(candle["high"] - prev_close), abs(candle["low"] - prev_close))

    def _calculate_ema(self, data, period):
        if len(data) < period:
            return np.mean(data)
        multiplier = 2 / (period + 1)
        ema = np.mean(data[:period])
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
