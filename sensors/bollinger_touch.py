"""
BollingerTouch Sensor (V3).
Logic: Price touches Bollinger Bands (mean reversion).

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class BollingerTouchV3(SensorV3):
    @property
    def name(self) -> str:
        return "BollingerTouch"

    def __init__(self, window=20, std_dev=2.5):
        self.window = window
        self.std_dev = std_dev
        # Buffer per timeframe (initialized lazily)
        self.buffers: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        """Get or create buffer for a timeframe."""
        if tf not in self.buffers:
            self.buffers[tf] = deque(maxlen=self.window)
        return self.buffers[tf]

    def calculate(self, context: dict) -> List[dict]:
        """Calculate signals for all monitored timeframes."""
        signals = []

        # Iterate over all timeframes this sensor monitors
        for tf in self.timeframes:
            candle = context.get(tf)
            if candle is None:
                continue  # TF not ready yet

            signal = self._calculate_for_tf(tf, candle)
            if signal:
                signals.append(signal)

        return signals if signals else None

    def _calculate_for_tf(self, tf: str, candle: dict) -> Optional[dict]:
        """Calculate Bollinger signal for a single timeframe."""
        buffer = self._get_buffer(tf)
        close = candle["close"]
        buffer.append(close)

        if len(buffer) < self.window:
            return None

        closes_arr = np.array(buffer)
        ma = np.mean(closes_arr)
        std = np.std(closes_arr, ddof=0)

        upper = ma + self.std_dev * std
        lower = ma - self.std_dev * std

        if close <= lower:
            return {
                "side": "LONG",
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"bb_lower": lower, "bb_ma": ma},
            }
        elif close >= upper:
            return {
                "side": "SHORT",
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"bb_upper": upper, "bb_ma": ma},
            }

        return None
