"""
Fakeout Sensor (V3).
Logic: Detects fakeout/false breakout reversals.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class FakeoutV3(SensorV3):
    @property
    def name(self) -> str:
        return "Fakeout"

    def __init__(self, lookback=10, breakout_threshold=0.002, reversal_body_pct=0.6):
        self.lookback = lookback
        self.breakout_threshold = breakout_threshold
        self.reversal_body_pct = reversal_body_pct
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback + 5)
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

        prev = list(buffer)[:-1]
        range_high = max(c["high"] for c in prev[-self.lookback :])
        range_low = min(c["low"] for c in prev[-self.lookback :])

        open_p, high, low, close = candle["open"], candle["high"], candle["low"], candle["close"]
        candle_range = high - low
        if candle_range == 0:
            return None

        body = abs(close - open_p)
        body_pct = body / candle_range

        # Bullish fakeout
        if low < range_low:
            broke_below = (range_low - low) / range_low > self.breakout_threshold
            if broke_below and close > range_low and close > open_p and body_pct > self.reversal_body_pct:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "bullish_fakeout"}}

        # Bearish fakeout
        if high > range_high:
            broke_above = (high - range_high) / range_high > self.breakout_threshold
            if broke_above and close < range_high and close < open_p and body_pct > self.reversal_body_pct:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "bearish_fakeout"}}

        return None
