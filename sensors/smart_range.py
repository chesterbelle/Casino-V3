"""
SmartRange Sensor (V3).
Logic: Smart range scalping within defined boundaries.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class SmartRangeV3(SensorV3):
    @property
    def name(self) -> str:
        return "SmartRange"

    def __init__(self, lookback=20, boundary_pct=0.1, momentum_period=5):
        self.lookback = lookback
        self.boundary_pct = boundary_pct
        self.momentum_period = momentum_period
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback + 10)
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

        candles = list(buffer)[:-1]
        highs = [c["high"] for c in candles[-self.lookback :]]
        lows = [c["low"] for c in candles[-self.lookback :]]
        range_high, range_low = max(highs), min(lows)
        range_size = range_high - range_low

        if range_size == 0:
            return None

        close, open_p = candle["close"], candle["open"]
        position = (close - range_low) / range_size

        recent = list(buffer)[-self.momentum_period :]
        if len(recent) < 2:
            return None

        momentum_up = close > recent[0]["close"]
        momentum_down = close < recent[0]["close"]

        if position < self.boundary_pct and close > open_p and momentum_up:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"position": position}}
        if position > (1 - self.boundary_pct) and close < open_p and momentum_down:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"position": position}}
        return None
