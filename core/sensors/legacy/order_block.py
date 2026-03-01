"""
OrderBlock Sensor (V3).
Logic: Breakout from tight consolidation block.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class OrderBlockV3(SensorV3):
    @property
    def name(self) -> str:
        return "OrderBlock"

    def __init__(self, block_size=3, max_range_pct=0.001, breakout_pct=0.003):
        self.block_size = block_size
        self.max_range_pct = max_range_pct
        self.breakout_pct = breakout_pct
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=20)
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
        buffer.append([candle["open"], candle["high"], candle["low"], candle["close"]])

        if len(buffer) < self.block_size + 1:
            return None

        block = list(buffer)[-(self.block_size + 1) : -1]
        block_high = max(c[1] for c in block)
        block_low = min(c[2] for c in block)
        avg_price = np.mean([c[3] for c in block])
        block_range_pct = (block_high - block_low) / avg_price

        if block_range_pct > self.max_range_pct:
            return None

        close = candle["close"]
        if close > block_high * (1 + self.breakout_pct):
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"block_range": block_range_pct}}
        if close < block_low * (1 - self.breakout_pct):
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"block_range": block_range_pct}}
        return None
