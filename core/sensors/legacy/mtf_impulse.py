"""
MTFImpulse Sensor (V3).
Logic: Multi-timeframe impulse detection using momentum alignment.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class MTFImpulseV3(SensorV3):
    @property
    def name(self) -> str:
        return "MTFImpulse"

    def __init__(self, momentum_period=10, impulse_threshold=0.003):
        self.momentum_period = momentum_period
        self.impulse_threshold = impulse_threshold
        self.closes: Dict[str, deque] = {}
        self.last_timestamps: Dict[str, any] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=self.momentum_period + 10)
        return self.closes[tf]

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

        # Skip duplicate timestamps
        ts = candle.get("timestamp")
        if ts == self.last_timestamps.get(tf):
            return None
        if not candle.get("is_complete", True):
            return None

        self.last_timestamps[tf] = ts
        buffer.append(candle["close"])

        if len(buffer) < self.momentum_period:
            return None

        momentum = self._calculate_momentum(list(buffer))
        if abs(momentum) < self.impulse_threshold:
            return None

        side = "LONG" if momentum > 0 else "SHORT"
        return {
            "side": side,
            "score": min(abs(momentum) / self.impulse_threshold, 2.0) / 2,
            "timeframe": tf,
            "metadata": {"momentum": momentum},
        }

    def _calculate_momentum(self, closes):
        if len(closes) < self.momentum_period:
            return 0
        old_price = closes[-self.momentum_period]
        return (closes[-1] - old_price) / old_price if old_price else 0
