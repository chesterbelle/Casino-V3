"""
VWAPMomentum Sensor (V3).
Logic: Detects momentum moves relative to VWAP.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class VWAPMomentumV3(SensorV3):
    @property
    def name(self) -> str:
        return "VWAPMomentum"

    def __init__(self, momentum_threshold=0.003, volume_factor=1.5, lookback=50):
        self.momentum_threshold = momentum_threshold
        self.volume_factor = volume_factor
        self.lookback = lookback
        self.volumes: Dict[str, deque] = {}
        self.cum_tp_vol: Dict[str, float] = {}
        self.cum_vol: Dict[str, float] = {}

    def _get_state(self, tf: str):
        if tf not in self.volumes:
            self.volumes[tf] = deque(maxlen=self.lookback + 10)
            self.cum_tp_vol[tf] = 0
            self.cum_vol[tf] = 0
        return self.volumes[tf]

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
        volumes = self._get_state(tf)
        tp = (candle["high"] + candle["low"] + candle["close"]) / 3
        vol = candle.get("volume", 1)
        volumes.append(vol)

        self.cum_tp_vol[tf] += tp * vol
        self.cum_vol[tf] += vol

        if len(volumes) < 20 or self.cum_vol[tf] == 0:
            return None

        vwap = self.cum_tp_vol[tf] / self.cum_vol[tf]
        distance_pct = (candle["close"] - vwap) / vwap if vwap > 0 else 0

        avg_vol = np.mean(list(volumes)[:-1]) if len(volumes) > 1 else 1
        vol_ok = vol > avg_vol * self.volume_factor
        close, open_p = candle["close"], candle["open"]

        if distance_pct > self.momentum_threshold and close > open_p and vol_ok:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"distance_pct": distance_pct}}
        if distance_pct < -self.momentum_threshold and close < open_p and vol_ok:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"distance_pct": distance_pct}}
        return None
