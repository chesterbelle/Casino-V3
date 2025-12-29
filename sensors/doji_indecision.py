"""
DojiIndecision Sensor (V3).
Logic: Doji indecision followed by strong breakout.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class DojiIndecisionV3(SensorV3):
    @property
    def name(self) -> str:
        return "DojiIndecision"

    def __init__(self, max_body_pct=0.001, breakout_body_pct=0.6, min_breakout_size=0.003):
        self.max_body_pct = max_body_pct
        self.breakout_body_pct = breakout_body_pct
        self.min_breakout_size = min_breakout_size
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
        if not prev:
            self.prev_candles[tf] = candle
            return None

        curr = candle
        prev_body = abs(prev["close"] - prev["open"])
        prev_range = prev["high"] - prev["low"]
        prev_body_pct = prev_body / prev["close"] if prev["close"] else 0

        if prev_range == 0 or prev_body_pct > self.max_body_pct:
            self.prev_candles[tf] = curr
            return None

        curr_body = abs(curr["close"] - curr["open"])
        curr_range = curr["high"] - curr["low"]

        if curr_range == 0:
            self.prev_candles[tf] = curr
            return None

        curr_body_ratio = curr_body / curr_range
        curr_body_pct = curr_body / curr["close"] if curr["close"] else 0

        signal = None
        if curr_body_ratio >= self.breakout_body_pct and curr_body_pct >= self.min_breakout_size:
            if curr["close"] > curr["open"] and curr["high"] > prev["high"]:
                signal = {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "doji_bullish"}}
            elif curr["close"] < curr["open"] and curr["low"] < prev["low"]:
                signal = {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "doji_bearish"}}

        self.prev_candles[tf] = curr
        return signal
