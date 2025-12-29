"""
VWAPDeviation Sensor (V3).
Tier 3: Good.
Logic: Price deviation from VWAP (Mean Reversion).

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class VWAPDeviationV3(SensorV3):
    @property
    def name(self) -> str:
        return "VWAPDeviation"

    def __init__(self, period=20, deviation_threshold=0.015):
        self.period = period
        self.deviation_threshold = deviation_threshold
        self.typical_prices: Dict[str, deque] = {}
        self.volumes: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.typical_prices:
            self.typical_prices[tf] = deque(maxlen=self.period)
            self.volumes[tf] = deque(maxlen=self.period)
        return self.typical_prices[tf], self.volumes[tf]

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
        tps, volumes = self._get_buffers(tf)
        tp = (candle["high"] + candle["low"] + candle["close"]) / 3
        tps.append(tp)
        volumes.append(candle["volume"])

        if len(tps) < self.period:
            return None

        tp_arr, vol_arr = np.array(tps), np.array(volumes)
        total_vol = np.sum(vol_arr)
        if total_vol == 0:
            return None

        vwap = np.sum(tp_arr * vol_arr) / total_vol
        deviation = (candle["close"] - vwap) / vwap

        if deviation < -self.deviation_threshold:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"deviation": deviation}}
        if deviation > self.deviation_threshold:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"deviation": deviation}}
        return None
