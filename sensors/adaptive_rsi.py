"""
AdaptiveRSI Sensor (V3).
Logic: Adaptive RSI with dynamic overbought/oversold levels.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class AdaptiveRSIV3(SensorV3):
    @property
    def name(self) -> str:
        return "AdaptiveRSI"

    def __init__(self, rsi_period=14, base_oversold=30, base_overbought=70, volatility_period=20):
        self.rsi_period = rsi_period
        self.base_oversold = base_oversold
        self.base_overbought = base_overbought
        self.volatility_period = volatility_period
        self.closes: Dict[str, deque] = {}
        self.gains: Dict[str, deque] = {}
        self.losses: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.closes:
            max_len = max(self.rsi_period, self.volatility_period) + 10
            self.closes[tf] = deque(maxlen=max_len)
            self.gains[tf] = deque(maxlen=self.rsi_period)
            self.losses[tf] = deque(maxlen=self.rsi_period)
        return self.closes[tf], self.gains[tf], self.losses[tf]

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
        closes, gains, losses = self._get_buffers(tf)
        closes.append(candle["close"])

        if len(closes) < self.rsi_period + 1:
            return None

        change = closes[-1] - closes[-2]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

        if len(gains) < self.rsi_period:
            return None

        avg_gain, avg_loss = np.mean(gains), np.mean(losses)
        rsi = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

        oversold, overbought = self._adaptive_levels(tf)

        if rsi < oversold:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"rsi": rsi, "level": oversold}}
        if rsi > overbought:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"rsi": rsi, "level": overbought}}
        return None

    def _adaptive_levels(self, tf: str):
        closes = list(self.closes[tf])
        if len(closes) < self.volatility_period:
            return self.base_oversold, self.base_overbought
        returns = np.diff(closes[-self.volatility_period :]) / np.array(closes[-self.volatility_period : -1])
        volatility = np.std(returns) * 100
        adjustment = min(volatility * 5, 15)
        return max(10, self.base_oversold - adjustment), min(90, self.base_overbought + adjustment)
