"""
HigherHighsLowerLows Sensor (V3).
Logic: Detects trend structure - HH/HL for uptrend, LH/LL for downtrend.
Provides early trend identification.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class HigherHighsLowerLowsV3(SensorV3):
    @property
    def name(self) -> str:
        return "HigherHighsLowerLows"

    def __init__(self, lookback=10):
        self.lookback = lookback
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback)
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

        if len(buffer) < 6:
            return None

        candles = list(buffer)

        # Find swing highs and lows
        swing_highs = []
        swing_lows = []

        for i in range(1, len(candles) - 1):
            # Swing high
            if candles[i]["high"] > candles[i - 1]["high"] and candles[i]["high"] > candles[i + 1]["high"]:
                swing_highs.append((i, candles[i]["high"]))
            # Swing low
            if candles[i]["low"] < candles[i - 1]["low"] and candles[i]["low"] < candles[i + 1]["low"]:
                swing_lows.append((i, candles[i]["low"]))

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return None

        # Check for HH/HL (uptrend) or LH/LL (downtrend)
        last_two_highs = [h[1] for h in swing_highs[-2:]]
        last_two_lows = [low[1] for low in swing_lows[-2:]]

        hh = last_two_highs[-1] > last_two_highs[-2]
        hl = last_two_lows[-1] > last_two_lows[-2]
        lh = last_two_highs[-1] < last_two_highs[-2]
        ll = last_two_lows[-1] < last_two_lows[-2]

        if hh and hl:
            side = "LONG"
            pattern = "higher_highs_higher_lows"
        elif lh and ll:
            side = "SHORT"
            pattern = "lower_highs_lower_lows"
        else:
            return None

        # Calculate structure strength
        high_diff = abs(last_two_highs[-1] - last_two_highs[-2]) / last_two_highs[-2]
        low_diff = abs(last_two_lows[-1] - last_two_lows[-2]) / last_two_lows[-2]
        strength = (high_diff + low_diff) / 2

        return {
            "side": side,
            "score": min(strength * 100, 1.0),
            "timeframe": tf,
            "metadata": {"pattern": pattern},
        }
