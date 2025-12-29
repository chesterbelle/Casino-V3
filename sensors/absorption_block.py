"""
AbsorptionBlock Sensor (V3).
Logic: Detects volume absorption patterns.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class AbsorptionBlockV3(SensorV3):
    @property
    def name(self) -> str:
        return "AbsorptionBlock"

    def __init__(self, volume_factor=2.0, body_factor=0.3, lookback=20):
        self.volume_factor = volume_factor
        self.body_factor = body_factor
        self.lookback = lookback
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

        candle_range = candle["high"] - candle["low"]
        if candle_range == 0:
            return None

        body = abs(candle["close"] - candle["open"])
        body_ratio = body / candle_range
        vol = candle.get("volume", 0)
        avg_vol = np.mean(list(volumes)[:-1]) if len(volumes) > 1 else 1

        if not (vol > avg_vol * self.volume_factor and body_ratio < self.body_factor):
            return None

        prev = list(candles)[-5:-1]
        if len(prev) < 3:
            return None
        closes = [c["close"] for c in prev]
        was_down = closes[-1] < closes[0]
        was_up = closes[-1] > closes[0]

        if was_down and candle["close"] > candle["open"]:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "bullish_absorption"}}
        if was_up and candle["close"] < candle["open"]:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "bearish_absorption"}}
        return None
