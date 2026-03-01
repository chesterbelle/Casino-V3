"""
WilliamsRReversion Sensor (V3).
Logic: Williams %R oversold/overbought.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class WilliamsRReversionV3(SensorV3):
    @property
    def name(self) -> str:
        return "WilliamsRReversion"

    def __init__(self, period=14, oversold=-80.0, overbought=-20.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.highs: Dict[str, deque] = {}
        self.lows: Dict[str, deque] = {}
        self.closes: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.highs:
            self.highs[tf] = deque(maxlen=self.period)
            self.lows[tf] = deque(maxlen=self.period)
            self.closes[tf] = deque(maxlen=self.period)
        return self.highs[tf], self.lows[tf], self.closes[tf]

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
        highs, lows, closes = self._get_buffers(tf)
        highs.append(candle["high"])
        lows.append(candle["low"])
        closes.append(candle["close"])

        if len(closes) < self.period:
            return None

        highest_high = max(highs)
        lowest_low = min(lows)

        if highest_high == lowest_low:
            return None

        williams_r = ((highest_high - closes[-1]) / (highest_high - lowest_low)) * -100

        if williams_r < self.oversold:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"williams_r": williams_r}}
        elif williams_r > self.overbought:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"williams_r": williams_r}}
        return None
