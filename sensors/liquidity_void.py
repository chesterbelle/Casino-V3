"""
LiquidityVoid Sensor (V3).
Logic: Detects liquidity voids (gaps) that price may revisit.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from .base import SensorV3

logger = logging.getLogger(__name__)


class LiquidityVoidV3(SensorV3):
    @property
    def name(self) -> str:
        return "LiquidityVoid"

    def __init__(self, gap_pct=0.002, max_volume_pct=0.5, lookback=20):
        self.gap_pct = gap_pct
        self.max_volume_pct = max_volume_pct
        self.lookback = lookback
        self.candles: Dict[str, deque] = {}
        self.volumes: Dict[str, deque] = {}
        self.voids: Dict[str, list] = {}

    def _get_state(self, tf: str):
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=self.lookback + 5)
            self.volumes[tf] = deque(maxlen=self.lookback + 5)
            self.voids[tf] = []
        return self.candles[tf], self.volumes[tf], self.voids[tf]

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
        candles, volumes, voids = self._get_state(tf)
        candles.append(candle)
        volumes.append(candle.get("volume", 0))

        if len(candles) < 2:
            return None

        self._detect_void(tf)
        return self._check_void_fill(tf, candle)

    def _detect_void(self, tf: str):
        candles, volumes, voids = self.candles[tf], self.volumes[tf], self.voids[tf]
        prev, curr = candles[-2], candles[-1]
        vol = curr.get("volume", 0)
        avg_vol = np.mean(list(volumes)[:-1]) if len(volumes) > 1 else 1
        if vol / avg_vol > self.max_volume_pct if avg_vol > 0 else True:
            return

        avg_price = (prev["close"] + curr["open"]) / 2

        if curr["low"] > prev["high"] and (curr["low"] - prev["high"]) / avg_price > self.gap_pct:
            voids.append({"top": curr["low"], "bottom": prev["high"], "dir": "up"})
        if curr["high"] < prev["low"] and (prev["low"] - curr["high"]) / avg_price > self.gap_pct:
            voids.append({"top": prev["low"], "bottom": curr["high"], "dir": "down"})

        if len(voids) > 5:
            self.voids[tf] = voids[-5:]

    def _check_void_fill(self, tf: str, candle):
        voids = self.voids[tf]
        close = candle["close"]
        for void in voids:
            if void["dir"] == "up":
                dist = (close - void["top"]) / close if close > 0 else 1
                if 0 < dist < 0.01:
                    return {"side": "SHORT", "score": 0.8, "timeframe": tf, "metadata": {"pattern": "void_fill"}}
            if void["dir"] == "down":
                dist = (void["bottom"] - close) / close if close > 0 else 1
                if 0 < dist < 0.01:
                    return {"side": "LONG", "score": 0.8, "timeframe": tf, "metadata": {"pattern": "void_fill"}}
        return None
