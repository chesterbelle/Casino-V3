"""
VolumeSpike Sensor (V3).
Logic: Detects volume spike reversals.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class VolumeSpikeV3(SensorV3):
    @property
    def name(self) -> str:
        return "VolumeSpike"

    def __init__(self, volume_multiplier=3.0, min_body_pct=0.004, lookback=20):
        self.volume_multiplier = volume_multiplier
        self.min_body_pct = min_body_pct
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

        if len(volumes) < self.lookback:
            return None

        volume = volumes[-1]
        avg_vol = np.mean(list(volumes)[:-1])
        if avg_vol == 0 or volume / avg_vol < self.volume_multiplier:
            return None

        body = abs(candle["close"] - candle["open"])
        avg_price = (candle["high"] + candle["low"]) / 2
        if body / avg_price < self.min_body_pct:
            return None

        # Check trend
        prev = list(candles)[-5:-1]
        if len(prev) < 3:
            return None
        closes = [c["close"] for c in prev]
        was_down = closes[-1] < closes[0]
        was_up = closes[-1] > closes[0]

        if was_down and candle["close"] > candle["open"]:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"volume_ratio": volume / avg_vol}}
        if was_up and candle["close"] < candle["open"]:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"volume_ratio": volume / avg_vol}}
        return None
