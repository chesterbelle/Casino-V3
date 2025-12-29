"""
VolatilityWakeup Sensor (V3).
Logic: Detects volatility expansion after compression.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class VolatilityWakeupV3(SensorV3):
    @property
    def name(self) -> str:
        return "VolatilityWakeup"

    def __init__(self, atr_period=14, expansion_factor=1.5, compression_lookback=10):
        self.atr_period = atr_period
        self.expansion_factor = expansion_factor
        self.compression_lookback = compression_lookback
        self.trs: Dict[str, deque] = {}
        self.candles: Dict[str, deque] = {}

    def _get_buffers(self, tf: str):
        max_len = self.atr_period + self.compression_lookback + 10
        if tf not in self.trs:
            self.trs[tf] = deque(maxlen=max_len)
            self.candles[tf] = deque(maxlen=max_len)
        return self.trs[tf], self.candles[tf]

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
        trs, candles = self._get_buffers(tf)
        candles.append(candle)
        tr = self._calculate_tr(tf, candle)
        trs.append(tr)

        if len(trs) < self.atr_period + self.compression_lookback:
            return None

        trs_list = list(trs)
        current_atr = np.mean(trs_list[-self.atr_period :])
        compression_trs = trs_list[-(self.atr_period + self.compression_lookback) : -self.atr_period]
        compression_atr = np.mean(compression_trs) if compression_trs else current_atr

        if compression_atr == 0 or current_atr / compression_atr < self.expansion_factor:
            return None

        side = "LONG" if candle["close"] > candle["open"] else "SHORT" if candle["close"] < candle["open"] else None
        if side:
            return {
                "side": side,
                "score": 1.0,
                "timeframe": tf,
                "metadata": {"expansion": current_atr / compression_atr},
            }
        return None

    def _calculate_tr(self, tf: str, candle):
        candles = self.candles[tf]
        high, low = candle["high"], candle["low"]
        if len(candles) < 2:
            return high - low
        prev_c = candles[-2]["close"]
        return max(high - low, abs(high - prev_c), abs(low - prev_c))
