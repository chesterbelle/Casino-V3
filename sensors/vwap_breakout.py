"""
VWAPBreakout Sensor (V3).
Logic: Detects breakouts from VWAP with volume confirmation.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class VWAPBreakoutV3(SensorV3):
    @property
    def name(self) -> str:
        return "VWAPBreakout"

    def __init__(self, std_dev_mult=1.0, volume_factor=1.2, lookback=50):
        self.std_dev_mult = std_dev_mult
        self.volume_factor = volume_factor
        self.lookback = lookback
        self.candles: Dict[str, deque] = {}
        self.volumes: Dict[str, deque] = {}
        self.typical_prices: Dict[str, deque] = {}
        self.cum_tp_vol: Dict[str, float] = {}
        self.cum_vol: Dict[str, float] = {}

    def _get_buffers(self, tf: str):
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback + 10)
            self.volumes[tf] = deque(maxlen=self.lookback + 10)
            self.typical_prices[tf] = deque(maxlen=self.lookback + 10)
            self.cum_tp_vol[tf] = 0
            self.cum_vol[tf] = 0
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
        vol = candle.get("volume", 1)

        tps.append(tp)
        volumes.append(vol)
        self.cum_tp_vol[tf] += tp * vol
        self.cum_vol[tf] += vol

        if len(tps) < 20 or self.cum_vol[tf] == 0:
            return None

        vwap = self.cum_tp_vol[tf] / self.cum_vol[tf]
        std = np.std(list(tps)) if len(tps) > 1 else 0
        upper, lower = vwap + self.std_dev_mult * std, vwap - self.std_dev_mult * std

        avg_vol = np.mean(list(volumes)[:-1]) if len(volumes) > 1 else 1
        vol_ok = vol > avg_vol * self.volume_factor
        close, open_p = candle["close"], candle["open"]

        if close > upper and close > open_p and vol_ok:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"vwap": vwap}}
        if close < lower and close < open_p and vol_ok:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"vwap": vwap}}
        return None
