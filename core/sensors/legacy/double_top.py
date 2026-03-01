"""
DoubleTop Sensor (V3).
Logic: M-pattern - two highs at similar levels with a trough between.
Classic bearish reversal pattern.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class DoubleTopV3(SensorV3):
    @property
    def name(self) -> str:
        return "DoubleTop"

    def __init__(self, lookback=20, tolerance_pct=0.005):
        self.lookback = lookback
        self.tolerance_pct = tolerance_pct
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback)
        return self.candles[tf]

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
        buffer.append(candle)

        if len(buffer) < 7:
            return None

        candles = list(buffer)
        lows = [c["low"] for c in candles]
        highs = [c["high"] for c in candles]
        closes = [c["close"] for c in candles]

        # Find highest point
        max_high = max(highs)

        # Find first top
        first_top_idx = None
        for i in range(len(highs) - 3):
            if highs[i] >= max_high * (1 - self.tolerance_pct):
                if i > 0 and highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                    first_top_idx = i
                    break

        if first_top_idx is None:
            return None

        # Find second top
        second_top_idx = None
        for i in range(first_top_idx + 3, len(highs)):
            if highs[i] >= highs[first_top_idx] * (1 - self.tolerance_pct):
                if i < len(highs) - 1 and highs[i] > highs[i - 1]:
                    second_top_idx = i
                    break

        if second_top_idx is None:
            return None

        # Must have a trough between tops
        mid_lows = lows[first_top_idx + 1 : second_top_idx]
        if not mid_lows:
            return None

        trough = min(mid_lows)
        top_avg = (highs[first_top_idx] + highs[second_top_idx]) / 2

        if trough > top_avg * 0.99:
            return None

        # Current price should be breaking below neckline
        if closes[-1] > trough:
            return None

        depth = (top_avg - trough) / top_avg

        return {
            "side": "SHORT",
            "score": min(depth * 10, 1.0),
            "timeframe": tf,
            "metadata": {
                "pattern": "double_top",
                "depth_pct": depth,
            },
        }
