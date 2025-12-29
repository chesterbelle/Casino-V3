"""
WyckoffSpring Sensor (V3).
Logic: Detects Wyckoff spring and upthrust patterns.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class WyckoffSpringV3(SensorV3):
    @property
    def name(self) -> str:
        return "WyckoffSpring"

    def __init__(self, lookback=20, volume_factor=1.5, reversal_threshold=0.002):
        self.lookback = lookback
        self.volume_factor = volume_factor
        self.reversal_threshold = reversal_threshold
        self.candles: Dict[str, deque] = {}
        self.volumes: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback + 5)
            self.volumes[tf] = deque(maxlen=self.lookback + 5)
        return self.candles[tf], self.volumes[tf]

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
        candles, volumes = self._get_buffers(tf)
        candles.append(candle)
        volumes.append(candle.get("volume", 0))

        if len(candles) < self.lookback:
            return None

        prev = list(candles)[:-1]
        support = min(c["low"] for c in prev[-self.lookback :])
        resistance = max(c["high"] for c in prev[-self.lookback :])

        high, low, close, vol = candle["high"], candle["low"], candle["close"], candle.get("volume", 0)
        avg_vol = np.mean(list(volumes)[:-1]) if len(volumes) > 1 else 1
        vol_spike = vol > avg_vol * self.volume_factor

        # Spring: Low pierces support, closes above
        if low < support:
            reversal_pct = (close - low) / low if low > 0 else 0
            if close > support and reversal_pct > self.reversal_threshold:
                return {
                    "side": "LONG",
                    "score": 1.0 if vol_spike else 0.7,
                    "timeframe": tf,
                    "metadata": {"pattern": "spring"},
                }

        # Upthrust: High pierces resistance, closes below
        if high > resistance:
            reversal_pct = (high - close) / high if high > 0 else 0
            if close < resistance and reversal_pct > self.reversal_threshold:
                return {
                    "side": "SHORT",
                    "score": 1.0 if vol_spike else 0.7,
                    "timeframe": tf,
                    "metadata": {"pattern": "upthrust"},
                }

        return None
