"""
InsideBarBreakout Sensor (V3).
Tier 3: Good.
Logic: Inside bar followed by breakout.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class InsideBarBreakoutV3(SensorV3):
    @property
    def name(self) -> str:
        return "InsideBarBreakout"

    def __init__(self, max_inside_range_pct=0.005, breakout_confirmation=True):
        self.max_inside_range_pct = max_inside_range_pct
        self.breakout_confirmation = breakout_confirmation
        self.candles: Dict[str, deque] = {}
        self.inside_bar_detected: Dict[str, bool] = {}
        self.inside_bar_levels: Dict[str, tuple] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=3)
            self.inside_bar_detected[tf] = False
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

        if len(buffer) < 3:
            return None

        curr, prev, prev_prev = buffer[-1], buffer[-2], buffer[-3]

        # Check for Inside Bar
        is_inside = prev["high"] < prev_prev["high"] and prev["low"] > prev_prev["low"]
        if is_inside:
            inside_range_pct = (prev["high"] - prev["low"]) / curr["close"] if curr["close"] else 0
            if inside_range_pct <= self.max_inside_range_pct:
                self.inside_bar_detected[tf] = True
                self.inside_bar_levels[tf] = (prev["high"], prev["low"])

        # Check Breakout
        if self.inside_bar_detected.get(tf):
            high, low = self.inside_bar_levels[tf]
            if curr["high"] > high and (not self.breakout_confirmation or curr["close"] > high):
                self.inside_bar_detected[tf] = False
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "inside_breakout"}}
            if curr["low"] < low and (not self.breakout_confirmation or curr["close"] < low):
                self.inside_bar_detected[tf] = False
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "inside_breakout"}}

        return None
