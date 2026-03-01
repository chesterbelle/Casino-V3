"""
RSIReversion Sensor (V3).
Logic: RSI oversold/overbought mean reversion.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class RSIReversionV3(SensorV3):
    @property
    def name(self) -> str:
        return "RSIReversion"

    def __init__(self, period=2, low=10.0, high=90.0):
        self.period = period
        self.low = low
        self.high = high
        # Buffer per timeframe
        self.buffers: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        """Get or create buffer for a timeframe."""
        if tf not in self.buffers:
            self.buffers[tf] = deque(maxlen=250)
        return self.buffers[tf]

    def calculate(self, context: dict) -> List[dict]:
        """Calculate signals for all monitored timeframes."""
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
        """Calculate RSI signal for a single timeframe."""
        buffer = self._get_buffer(tf)
        close = candle["close"]
        buffer.append(close)

        if len(buffer) < self.period + 1:
            return None

        rsi = self._compute_rsi(buffer)

        if rsi < self.low:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"rsi": rsi}}
        elif rsi > self.high:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"rsi": rsi}}

        return None

    def _compute_rsi(self, buffer: deque) -> float:
        prices_arr = np.array(buffer)
        delta = np.diff(prices_arr)
        gains = np.maximum(delta, 0)
        losses = np.abs(np.minimum(delta, 0))

        avg_gain = np.mean(gains[-self.period :])
        avg_loss = np.mean(losses[-self.period :])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
