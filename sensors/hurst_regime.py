"""
HurstRegime Sensor (V3).
Logic: Hurst exponent for trend/mean-reversion regime detection.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class HurstRegimeV3(SensorV3):
    @property
    def name(self) -> str:
        return "HurstRegime"

    def __init__(self, period=50, trend_threshold=0.6, reversion_threshold=0.4):
        self.period = period
        self.trend_threshold = trend_threshold
        self.reversion_threshold = reversion_threshold
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

        hurst = self._calculate_hurst(tf)
        if hurst is None or hurst <= self.trend_threshold:
            return None

        closes = list(buffer)
        recent_dir = closes[-1] - closes[-5] if len(closes) >= 5 else 0

        if recent_dir > 0:
            return {"side": "LONG", "score": 0.8, "timeframe": tf, "metadata": {"hurst": hurst, "regime": "trending"}}
        if recent_dir < 0:
            return {"side": "SHORT", "score": 0.8, "timeframe": tf, "metadata": {"hurst": hurst, "regime": "trending"}}
        return None

    def _calculate_hurst(self, tf: str):
        closes = np.array(list(self.closes[tf])[-self.period :])
        if len(closes) < 20:
            return None

        returns = np.diff(np.log(closes))
        if len(returns) < 10:
            return None

        rs_values, ns = [], []
        for n in [10, 20, 30, 40]:
            if n > len(returns):
                continue
            num_chunks = len(returns) // n
            if num_chunks == 0:
                continue
            chunk_rs = []
            for i in range(num_chunks):
                chunk = returns[i * n : (i + 1) * n]
                mean_adj = chunk - np.mean(chunk)
                cumsum = np.cumsum(mean_adj)
                R = np.max(cumsum) - np.min(cumsum)
                S = np.std(chunk, ddof=1)
                if S > 0:
                    chunk_rs.append(R / S)
            if chunk_rs:
                rs_values.append(np.mean(chunk_rs))
                ns.append(n)

        if len(rs_values) < 2:
            return 0.5
        return max(0.0, min(1.0, np.polyfit(np.log(ns), np.log(rs_values), 1)[0]))
