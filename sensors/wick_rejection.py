"""
WickRejection Sensor (V3).
Logic: Detects strong wick rejection patterns.

Multi-TF: Monitors multiple timeframes (stateless per candle).
"""

import logging
from typing import List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class WickRejectionV3(SensorV3):
    @property
    def name(self) -> str:
        return "WickRejection"

    def __init__(self, wick_ratio=2.0, min_wick_pct=0.003):
        self.wick_ratio = wick_ratio
        self.min_wick_pct = min_wick_pct

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
        open_p, high, low, close = candle["open"], candle["high"], candle["low"], candle["close"]
        body = abs(close - open_p) or 0.0001
        upper_wick = high - max(open_p, close)
        lower_wick = min(open_p, close) - low
        avg_price = (high + low) / 2

        # Bullish rejection
        if lower_wick > body * self.wick_ratio and lower_wick / avg_price > self.min_wick_pct:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"wick_ratio": lower_wick / body}}

        # Bearish rejection
        if upper_wick > body * self.wick_ratio and upper_wick / avg_price > self.min_wick_pct:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"wick_ratio": upper_wick / body}}

        return None
