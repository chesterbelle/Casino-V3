"""
RailsPattern Sensor (V3).
Tier 1: 69% Win Rate.
Logic: Two consecutive candles with similar range but opposite direction.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class RailsPatternV3(SensorV3):
    @property
    def name(self) -> str:
        return "RailsPattern"

    def __init__(self, max_diff_pct=0.1):
        self.max_diff_pct = max_diff_pct
        self.prev_candles: Dict[str, dict] = {}

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
        prev = self.prev_candles.get(tf)
        self.prev_candles[tf] = candle

        if not prev:
            return None

        prev_body = abs(prev["close"] - prev["open"])
        curr_body = abs(candle["close"] - candle["open"])

        if prev_body == 0:
            return None

        diff_pct = abs(prev_body - curr_body) / prev_body
        if diff_pct >= self.max_diff_pct:
            return None

        # Bullish Rails: Red then Green
        if prev["close"] < prev["open"] and candle["close"] > candle["open"]:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"diff_pct": diff_pct}}

        # Bearish Rails: Green then Red
        if prev["close"] > prev["open"] and candle["close"] < candle["open"]:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"diff_pct": diff_pct}}

        return None
