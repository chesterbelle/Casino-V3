"""
NarrowRange7 (NR7) Sensor (V3).
Logic: Current bar has the smallest range of the last 7 bars.
This indicates volatility compression, often preceding a breakout.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class NarrowRange7V3(SensorV3):
    @property
    def name(self) -> str:
        return "NarrowRange7"

    def __init__(self, lookback=7):
        self.lookback = lookback
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

        if len(buffer) < self.lookback:
            return None

        # Calculate ranges for all candles
        ranges = [c["high"] - c["low"] for c in buffer]
        current_range = ranges[-1]

        # Current bar must have smallest range
        if current_range >= min(ranges[:-1]):
            return None

        # Determine direction based on recent trend
        first_close = buffer[0]["close"]
        last_close = buffer[-1]["close"]

        # NR7 is a breakout setup - signal in same direction as compression
        if last_close > first_close:
            side = "LONG"  # Expect breakout up
        else:
            side = "SHORT"  # Expect breakout down

        compression_ratio = current_range / max(ranges)

        return {
            "side": side,
            "score": 1.0 - compression_ratio,  # More compression = higher score
            "timeframe": tf,
            "metadata": {
                "pattern": "nr7",
                "compression_ratio": compression_ratio,
            },
        }
