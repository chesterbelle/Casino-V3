"""
BollingerRejection Sensor (V3).
Logic: Detects price rejection at Bollinger Band edges.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class BollingerRejectionV3(SensorV3):
    @property
    def name(self) -> str:
        return "BollingerRejection"

    def __init__(self, period=20, std_dev=2.0, rejection_threshold=0.002):
        self.period = period
        self.std_dev = std_dev
        self.rejection_threshold = rejection_threshold
        self.closes: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=self.period + 10)
        return self.closes[tf]

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
        buffer.append(candle["close"])

        if len(buffer) < self.period:
            return None

        closes = list(buffer)[-self.period :]
        sma = np.mean(closes)
        std = np.std(closes)
        upper_band = sma + (self.std_dev * std)
        lower_band = sma - (self.std_dev * std)

        high, low, close, open_p = candle["high"], candle["low"], candle["close"], candle["open"]

        if low < lower_band:
            rejection_pct = (close - low) / low if low > 0 else 0
            if close > lower_band and rejection_pct > self.rejection_threshold and close > open_p:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "lower_rejection"}}

        if high > upper_band:
            rejection_pct = (high - close) / high if high > 0 else 0
            if close < upper_band and rejection_pct > self.rejection_threshold and close < open_p:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "upper_rejection"}}

        return None
