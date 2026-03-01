"""
SupportResistance Sensor (V3).
Logic: Detects bounces off support and resistance levels.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class SupportResistanceV3(SensorV3):
    @property
    def name(self) -> str:
        return "SupportResistance"

    def __init__(self, lookback=20, touch_tolerance=0.001, bounce_threshold=0.002):
        self.lookback = lookback
        self.touch_tolerance = touch_tolerance
        self.bounce_threshold = bounce_threshold
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

        support_levels, resistance_levels = self._find_sr_levels(tf)
        return self._check_bounce(tf, candle, support_levels, resistance_levels)

    def _find_sr_levels(self, tf: str):
        candles = list(self.candles[tf])[:-1]
        support, resistance = [], []

        for i in range(2, len(candles) - 2):
            if all(candles[i]["low"] < candles[i + j]["low"] for j in [-2, -1, 1, 2]):
                support.append(candles[i]["low"])
            if all(candles[i]["high"] > candles[i + j]["high"] for j in [-2, -1, 1, 2]):
                resistance.append(candles[i]["high"])

        if candles:
            resistance.append(max(c["high"] for c in candles[-10:]))
            support.append(min(c["low"] for c in candles[-10:]))
        return support, resistance

    def _check_bounce(self, tf: str, candle, support_levels, resistance_levels):
        close, open_p, high, low = candle["close"], candle["open"], candle["high"], candle["low"]

        for level in support_levels:
            if level == 0:
                continue
            if abs(low - level) / level < self.touch_tolerance:
                bounce = (close - low) / low if low > 0 else 0
                if bounce > self.bounce_threshold and close > open_p:
                    return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"level": level}}

        for level in resistance_levels:
            if level == 0:
                continue
            if abs(high - level) / level < self.touch_tolerance:
                bounce = (high - close) / high if high > 0 else 0
                if bounce > self.bounce_threshold and close < open_p:
                    return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"level": level}}
        return None
