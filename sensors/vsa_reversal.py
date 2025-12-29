"""
VSAReversal Sensor (V3).
Logic: Volume Spread Analysis reversal detection.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class VSAReversalV3(SensorV3):
    @property
    def name(self) -> str:
        return "VSAReversal"

    def __init__(self, lookback=20, volume_threshold=1.5, spread_threshold=0.7):
        self.lookback = lookback
        self.volume_threshold = volume_threshold
        self.spread_threshold = spread_threshold
        self.candles: Dict[str, deque] = {}
        self.volumes: Dict[str, deque] = {}
        self.spreads: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback + 5)
            self.volumes[tf] = deque(maxlen=self.lookback + 5)
            self.spreads[tf] = deque(maxlen=self.lookback + 5)
        return self.candles[tf], self.volumes[tf], self.spreads[tf]

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
        candles, volumes, spreads = self._get_buffers(tf)
        spread = candle["high"] - candle["low"]
        candles.append(candle)
        volumes.append(candle.get("volume", 0))
        spreads.append(spread)

        if len(volumes) < self.lookback:
            return None

        vol = volumes[-1]
        avg_vol = np.mean(list(volumes)[:-1])
        avg_spread = np.mean(list(spreads)[:-1])
        if avg_vol == 0 or avg_spread == 0:
            return None

        vol_ratio = vol / avg_vol
        spread_ratio = spread / avg_spread

        prev = list(candles)[-5:-1]
        if len(prev) < 3:
            return None
        closes = [c["close"] for c in prev]
        was_down = closes[-1] < closes[0]
        was_up = closes[-1] > closes[0]

        if was_down and vol_ratio > self.volume_threshold and spread_ratio < self.spread_threshold:
            if candle["close"] > candle["open"]:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "stopping_volume"}}
        if was_up and vol_ratio > self.volume_threshold and spread_ratio < self.spread_threshold:
            if candle["close"] < candle["open"]:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"pattern": "no_demand"}}
        return None
