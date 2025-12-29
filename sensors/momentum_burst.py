"""
MomentumBurst Sensor (V3).
Logic: Sudden RSI acceleration (burst detection).

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class MomentumBurstV3(SensorV3):
    @property
    def name(self) -> str:
        return "MomentumBurst"

    def __init__(self, rsi_period=14, burst_threshold=15.0):
        self.rsi_period = rsi_period
        self.burst_threshold = burst_threshold
        self.closes: Dict[str, deque] = {}
        self.gains: Dict[str, deque] = {}
        self.losses: Dict[str, deque] = {}
        self.prev_rsi: Dict[str, float] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=self.rsi_period + 1)
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
        close = candle["close"]
        closes.append(close)

        if len(closes) < self.rsi_period:
            return None

        current_rsi = self._calculate_rsi(tf, close)

        if tf not in self.prev_rsi:
            self.prev_rsi[tf] = current_rsi
            return None

        rsi_delta = current_rsi - self.prev_rsi[tf]
        self.prev_rsi[tf] = current_rsi

        if abs(rsi_delta) > self.burst_threshold:
            if rsi_delta > 0 and current_rsi < 60:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"rsi_delta": rsi_delta}}
            elif rsi_delta < 0 and current_rsi > 40:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"rsi_delta": rsi_delta}}
        return None

    def _calculate_rsi(self, tf: str, current_close):
        closes, gains, losses = self._get_buffers(tf)
        if len(closes) < 2:
            return 50.0

        delta = current_close - closes[-2]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

        if len(gains) < self.rsi_period:
            return 50.0

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
