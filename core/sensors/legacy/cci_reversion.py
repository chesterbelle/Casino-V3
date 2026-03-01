"""
CCIReversion Sensor (V3).
Logic: Commodity Channel Index oversold/overbought.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class CCIReversionV3(SensorV3):
    @property
    def name(self) -> str:
        return "CCIReversion"

    def __init__(self, period=20, oversold=-100.0, overbought=100.0, constant=0.015):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.constant = constant
        self.buffers: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.buffers:
            self.buffers[tf] = deque(maxlen=self.period)
        return self.buffers[tf]

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
        typical_price = (candle["high"] + candle["low"] + candle["close"]) / 3
        buffer.append(typical_price)

        if len(buffer) < self.period:
            return None

        tp_array = np.array(buffer)
        sma_tp = np.mean(tp_array)
        mean_deviation = np.mean(np.abs(tp_array - sma_tp))

        if mean_deviation == 0:
            return None

        cci = (buffer[-1] - sma_tp) / (self.constant * mean_deviation)

        if cci < self.oversold:
            return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"cci": cci}}
        elif cci > self.overbought:
            return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"cci": cci}}
        return None
