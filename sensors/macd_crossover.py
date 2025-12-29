"""
MACDCrossover Sensor (V3).
Logic: MACD histogram crosses zero line.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class MACDCrossoverV3(SensorV3):
    @property
    def name(self) -> str:
        return "MACDCrossover"

    def __init__(self, short_period=12, long_period=26, signal_period=9):
        self.short_period = short_period
        self.long_period = long_period
        self.signal_period = signal_period
        self.closes: Dict[str, deque] = {}
        self.ema_short: Dict[str, float] = {}
        self.ema_long: Dict[str, float] = {}
        self.signal_line: Dict[str, float] = {}
        self.macd_values: Dict[str, deque] = {}
        self.prev_hist: Dict[str, float] = {}

    def _get_buffer(self, tf: str):
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=self.long_period + self.signal_period)
            self.macd_values[tf] = deque(maxlen=self.signal_period)
        return self.closes[tf], self.macd_values[tf]

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
        closes, macd_vals = self._get_buffer(tf)
        close = candle["close"]
        closes.append(close)

        if len(closes) < self.long_period:
            return None

        self.ema_short[tf] = self._compute_ema(self.ema_short.get(tf), close, self.short_period, list(closes))
        self.ema_long[tf] = self._compute_ema(self.ema_long.get(tf), close, self.long_period, list(closes))

        macd_line = self.ema_short[tf] - self.ema_long[tf]
        macd_vals.append(macd_line)

        if len(macd_vals) < self.signal_period:
            return None

        self.signal_line[tf] = self._compute_ema(
            self.signal_line.get(tf), macd_line, self.signal_period, list(macd_vals)
        )
        histogram = macd_line - self.signal_line[tf]

        prev = self.prev_hist.get(tf)
        self.prev_hist[tf] = histogram

        if prev is not None:
            if histogram > 0 and prev <= 0:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"histogram": histogram}}
            elif histogram < 0 and prev >= 0:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"histogram": histogram}}
        return None

    def _compute_ema(self, previous, value, period, seed):
        if previous is None:
            return sum(seed[-period:]) / period if len(seed) >= period else value
        k = 2 / (period + 1)
        return value * k + previous * (1 - k)
