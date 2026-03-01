"""
StochasticReversion Sensor (V3).
Logic: Stochastic oscillator oversold/overbought.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class StochasticReversionV3(SensorV3):
    @property
    def name(self) -> str:
        return "StochasticReversion"

    def __init__(self, k_period=14, d_period=3, low_threshold=20.0, high_threshold=80.0):
        self.k_period = k_period
        self.d_period = d_period
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        # Buffers per timeframe
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.closes: Dict[str, deque] = {}
        self.k_values: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.highs:
            self.highs[tf] = deque(maxlen=self.k_period)
            self.lows[tf] = deque(maxlen=self.k_period)
            self.closes[tf] = deque(maxlen=self.k_period)
            self.k_values[tf] = deque(maxlen=self.d_period)
        return self.highs[tf], self.lows[tf], self.closes[tf], self.k_values[tf]

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
        """Calculate Stochastic signal for a single timeframe."""
        highs, lows, closes, k_vals = self._get_buffers(tf)

        highs.append(candle["high"])
        lows.append(candle["low"])
        closes.append(candle["close"])

        if len(closes) < self.k_period:
            return None

        k = self._compute_k(highs, lows, closes)
        k_vals.append(k)

        if len(k_vals) < self.d_period:
            return None

        d = np.mean(k_vals)

        if k < self.low_threshold and d < self.low_threshold:
            return {
                "side": "LONG",
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"stoch_k": k, "stoch_d": d},
            }
        elif k > self.high_threshold and d > self.high_threshold:
            return {
                "side": "SHORT",
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"stoch_k": k, "stoch_d": d},
            }

        return None

    def _compute_k(self, highs, lows, closes) -> float:
        highest_high = max(highs)
        lowest_low = min(lows)
        current_close = closes[-1]

        if highest_high == lowest_low:
            return 50.0

        return ((current_close - lowest_low) / (highest_high - lowest_low)) * 100
