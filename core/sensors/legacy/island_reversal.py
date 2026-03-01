"""
IslandReversal Sensor (V3).
Logic: Price isolated by gaps on both sides.
Strong reversal signal when price gaps away from previous trend.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class IslandReversalV3(SensorV3):
    @property
    def name(self) -> str:
        return "IslandReversal"

    def __init__(self, gap_threshold_pct=0.001):
        self.gap_threshold_pct = gap_threshold_pct  # 0.1% minimum gap
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=5)
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

        if len(buffer) < 4:
            return None

        candles = list(buffer)

        # Check for bearish island (gap up then gap down)
        # Pattern: [pre] gap_up [island] gap_down [current]
        for i in range(1, len(candles) - 1):
            prev = candles[i - 1]
            island = candles[i]
            current = candles[i + 1] if i + 1 < len(candles) else candle

            # Gap up before island
            gap_up = island["low"] > prev["high"]
            gap_up_size = (island["low"] - prev["high"]) / prev["high"]

            # Gap down after island
            gap_down = current["high"] < island["low"]
            gap_down_size = (island["low"] - current["high"]) / island["low"]

            if gap_up and gap_up_size > self.gap_threshold_pct and gap_down and gap_down_size > self.gap_threshold_pct:
                return {
                    "side": "SHORT",
                    "score": min((gap_up_size + gap_down_size) * 50, 1.0),
                    "timeframe": tf,
                    "metadata": {"pattern": "bearish_island"},
                }

        # Check for bullish island (gap down then gap up)
        for i in range(1, len(candles) - 1):
            prev = candles[i - 1]
            island = candles[i]
            current = candles[i + 1] if i + 1 < len(candles) else candle

            gap_down = island["high"] < prev["low"]
            gap_down_size = (prev["low"] - island["high"]) / prev["low"]

            gap_up = current["low"] > island["high"]
            gap_up_size = (current["low"] - island["high"]) / island["high"]

            if gap_down and gap_down_size > self.gap_threshold_pct and gap_up and gap_up_size > self.gap_threshold_pct:
                return {
                    "side": "LONG",
                    "score": min((gap_down_size + gap_up_size) * 50, 1.0),
                    "timeframe": tf,
                    "metadata": {"pattern": "bullish_island"},
                }

        return None
