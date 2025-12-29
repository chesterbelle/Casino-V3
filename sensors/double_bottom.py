"""
DoubleBottom Sensor (V3).
Logic: W-pattern - two lows at similar levels with a peak between.
Classic bullish reversal pattern.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class DoubleBottomV3(SensorV3):
    @property
    def name(self) -> str:
        return "DoubleBottom"

    def __init__(self, lookback=20, tolerance_pct=0.005):
        self.lookback = lookback
        self.tolerance_pct = tolerance_pct  # 0.5% tolerance for matching lows
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

        if len(buffer) < 7:  # Minimum for W pattern
            return None

        candles = list(buffer)
        lows = [c["low"] for c in candles]
        highs = [c["high"] for c in candles]
        closes = [c["close"] for c in candles]

        # Find two lowest points
        min_low = min(lows)

        # Find first bottom
        first_bottom_idx = None
        for i in range(len(lows) - 3):
            if lows[i] <= min_low * (1 + self.tolerance_pct):
                # Check it's a local low
                if i > 0 and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                    first_bottom_idx = i
                    break

        if first_bottom_idx is None:
            return None

        # Find second bottom (at least 3 bars later)
        second_bottom_idx = None
        for i in range(first_bottom_idx + 3, len(lows)):
            if lows[i] <= lows[first_bottom_idx] * (1 + self.tolerance_pct):
                if i < len(lows) - 1 and lows[i] < lows[i - 1]:
                    second_bottom_idx = i
                    break

        if second_bottom_idx is None:
            return None

        # Must have a peak between bottoms
        mid_highs = highs[first_bottom_idx + 1 : second_bottom_idx]
        if not mid_highs:
            return None

        peak = max(mid_highs)
        bottom_avg = (lows[first_bottom_idx] + lows[second_bottom_idx]) / 2

        # Peak must be significantly above bottoms
        if peak < bottom_avg * 1.01:  # At least 1% higher
            return None

        # Current price should be breaking above the neckline (peak)
        if closes[-1] < peak:
            return None

        depth = (peak - bottom_avg) / peak

        return {
            "side": "LONG",
            "score": min(depth * 10, 1.0),
            "timeframe": tf,
            "metadata": {
                "pattern": "double_bottom",
                "depth_pct": depth,
            },
        }
