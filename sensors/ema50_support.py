"""
EMA50Support Sensor (V3).
Tier 2: Excellent.
Logic: Bounces off EMA50 in trend.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class EMA50SupportV3(SensorV3):
    @property
    def name(self) -> str:
        return "EMA50Support"

    def __init__(self, ema_period=50, tolerance_pct=0.001):
        self.ema_period = ema_period
        self.tolerance_pct = tolerance_pct
        self.closes: Dict[str, deque] = {}
        self.ema_vals: Dict[str, float] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.closes:
            self.closes[tf] = deque(maxlen=self.ema_period + 10)
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
        close, high, low, open_p = candle["close"], candle["high"], candle["low"], candle["open"]
        buffer.append(close)
        self._update_ema(tf, close)

        ema = self.ema_vals.get(tf)
        if ema is None or len(buffer) < self.ema_period:
            return None

        touch_threshold = ema * self.tolerance_pct

        # LONG: Low touches EMA, Close respects it
        if low <= (ema + touch_threshold) and close >= (ema * 0.999):
            is_bullish = close > open_p
            is_hammer = (min(close, open_p) - low) > abs(close - open_p)
            if is_bullish or is_hammer:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"ema": ema}}

        # SHORT: High touches EMA, Close respects it
        if high >= (ema - touch_threshold) and close <= (ema * 1.001):
            is_bearish = close < open_p
            is_star = (high - max(close, open_p)) > abs(close - open_p)
            if is_bearish or is_star:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"ema": ema}}

        return None

    def _update_ema(self, tf: str, close: float):
        k = 2 / (self.ema_period + 1)
        if tf not in self.ema_vals:
            self.ema_vals[tf] = close
        else:
            self.ema_vals[tf] = (close * k) + (self.ema_vals[tf] * (1 - k))
