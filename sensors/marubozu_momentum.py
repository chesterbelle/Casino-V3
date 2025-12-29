"""
MarubozuMomentum Sensor (V3).
Tier 2: Excellent.
Logic: Strong directional candles with minimal wicks.

Multi-TF: Monitors multiple timeframes (stateless).
"""

import logging
from typing import List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class MarubozuMomentumV3(SensorV3):
    @property
    def name(self) -> str:
        return "MarubozuMomentum"

    def __init__(self, min_body_to_range=0.8, min_body_size_pct=0.004):
        self.min_body_to_range = min_body_to_range
        self.min_body_size_pct = min_body_size_pct

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
        open_p = candle["open"]
        close = candle["close"]
        high = candle["high"]
        low = candle["low"]

        total_range = high - low
        if total_range == 0:
            return None

        body = abs(close - open_p)
        body_to_range = body / total_range

        if body_to_range < self.min_body_to_range:
            return None

        body_pct = body / close
        if body_pct < self.min_body_size_pct:
            return None

        if close > open_p:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"body_pct": body_pct}}
        elif close < open_p:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"body_pct": body_pct}}
        return None
