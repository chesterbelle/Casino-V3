"""
EngulfingPattern Sensor (V3).
Tier 3: Good.
Logic: Engulfing candle with volume confirmation.

Multi-TF: Monitors multiple timeframes with independent state per TF.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class EngulfingPatternV3(SensorV3):
    @property
    def name(self) -> str:
        return "EngulfingPattern"

    def __init__(self, volume_multiplier=1.5, min_body_pct=0.002):
        self.volume_multiplier = volume_multiplier
        self.min_body_pct = min_body_pct
        # State per timeframe
        self.volumes: Dict[str, deque] = {}
        self.prev_candles: Dict[str, dict] = {}

    def _get_volumes(self, tf: str) -> deque:
        if tf not in self.volumes:
            self.volumes[tf] = deque(maxlen=10)
        return self.volumes[tf]

    def calculate(self, context: dict) -> List[dict]:
        """Calculate signals for all monitored timeframes."""
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
        """Calculate Engulfing signal for a single timeframe."""
        volumes = self._get_volumes(tf)
        volume = candle["volume"]
        volumes.append(volume)

        prev = self.prev_candles.get(tf)
        if not prev or len(volumes) < 10:
            self.prev_candles[tf] = candle
            return None

        curr = candle
        curr_open = curr["open"]
        curr_close = curr["close"]
        curr_body = curr_close - curr_open
        curr_body_size = abs(curr_body)

        prev_open = prev["open"]
        prev_close = prev["close"]
        prev_body = prev_close - prev_open
        prev_body_size = abs(prev_body)

        # Check min body size
        if curr_body_size / curr_close < self.min_body_pct:
            self.prev_candles[tf] = curr
            return None

        # Check Volume
        avg_vol = np.mean(list(volumes)[:-1])
        if volume < avg_vol * self.volume_multiplier:
            self.prev_candles[tf] = curr
            return None

        signal = None

        # Bullish Engulfing
        if (
            prev_body < 0
            and curr_body > 0
            and curr_open <= prev_close
            and curr_close >= prev_open
            and curr_body_size > prev_body_size
        ):
            signal = {
                "side": "LONG",
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"pattern": "bullish_engulfing"},
            }

        # Bearish Engulfing
        elif (
            prev_body > 0
            and curr_body < 0
            and curr_open >= prev_close
            and curr_close <= prev_open
            and curr_body_size > prev_body_size
        ):
            signal = {
                "side": "SHORT",
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"pattern": "bearish_engulfing"},
            }

        self.prev_candles[tf] = curr
        return signal
