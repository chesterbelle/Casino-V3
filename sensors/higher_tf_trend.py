"""
HigherTFTrend Sensor (V3).
Logic: Confirms trend using higher timeframe EMA alignment.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class HigherTFTrendV3(SensorV3):
    @property
    def name(self) -> str:
        return "HigherTFTrend"

    def __init__(self, ema_period=20, lookback=3):
        self.ema_period = ema_period
        self.lookback = lookback
        self.htf_candles: Dict[str, deque] = {}
        self.htf_emas: Dict[str, deque] = {}
        self.last_timestamps: Dict[str, any] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.htf_candles:
            self.htf_candles[tf] = deque(maxlen=self.ema_period + self.lookback + 10)
            self.htf_emas[tf] = deque(maxlen=self.lookback + 5)
        return self.htf_candles[tf], self.htf_emas[tf]

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
        candles, emas = self._get_buffers(tf)

        # Skip if already processed this timestamp
        ts = candle.get("timestamp")
        if ts == self.last_timestamps.get(tf):
            return None
        if not candle.get("is_complete", True):
            return None

        self.last_timestamps[tf] = ts
        candles.append(candle)

        # Calculate EMA
        if len(candles) >= self.ema_period:
            ema = self._calculate_ema(tf)
            if ema is not None:
                emas.append(ema)

        if len(emas) < self.lookback:
            return None

        return self._check_trend(tf, candle)

    def _calculate_ema(self, tf: str):
        closes = [c["close"] for c in self.htf_candles[tf]]
        if len(closes) < self.ema_period:
            return None
        multiplier = 2 / (self.ema_period + 1)
        ema = np.mean(closes[: self.ema_period])
        for price in closes[self.ema_period :]:
            ema = (price - ema) * multiplier + ema
        return ema

    def _check_trend(self, tf: str, candle: dict):
        emas = list(self.htf_emas[tf])[-self.lookback :]
        if len(emas) < self.lookback:
            return None

        current_close = candle["close"]
        current_ema = emas[-1]

        ema_rising = all(emas[i] < emas[i + 1] for i in range(len(emas) - 1))
        ema_falling = all(emas[i] > emas[i + 1] for i in range(len(emas) - 1))

        if ema_rising and current_close > current_ema:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"trend": "bullish"}}
        if ema_falling and current_close < current_ema:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"trend": "bearish"}}
        return None
