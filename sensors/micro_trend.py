"""
MicroTrend Sensor (V3).
Logic: Detects micro trend pullbacks for scalping.

Multi-TF: Monitors multiple timeframes with independent buffers.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class MicroTrendV3(SensorV3):
    @property
    def name(self) -> str:
        return "MicroTrend"

    def __init__(self, trend_period=10, pullback_period=3, min_trend_pct=0.002):
        self.trend_period = trend_period
        self.pullback_period = pullback_period
        self.min_trend_pct = min_trend_pct
        self.candles: Dict[str, deque] = {}

    def _get_buffer(self, tf: str) -> deque:
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.trend_period + self.pullback_period + 5)
        return self.candles[tf]

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
        buffer.append(candle)

        if len(buffer) < self.trend_period + self.pullback_period:
            return None

        candles = list(buffer)
        trend_candles = candles[: self.trend_period]
        pullback_candles = candles[self.trend_period :]

        trend_start = trend_candles[0]["close"]
        trend_end = trend_candles[-1]["close"]
        trend_pct = (trend_end - trend_start) / trend_start if trend_start > 0 else 0

        pullback_closes = [c["close"] for c in pullback_candles]

        # Uptrend pullback
        if trend_pct > self.min_trend_pct:
            is_pullback = pullback_closes[-1] < pullback_closes[0]
            if is_pullback and candle["close"] > candle["open"]:
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"trend_pct": trend_pct}}

        # Downtrend pullback
        if trend_pct < -self.min_trend_pct:
            is_pullback = pullback_closes[-1] > pullback_closes[0]
            if is_pullback and candle["close"] < candle["open"]:
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"trend_pct": trend_pct}}

        return None
