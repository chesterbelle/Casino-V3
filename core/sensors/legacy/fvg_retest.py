"""
FVGRetest Sensor (V3).
Logic: Fair Value Gap retest detection.

Multi-TF: Monitors multiple timeframes with independent state.
"""

import logging
from collections import deque
from typing import Dict, List, Optional

from .base import SensorV3

logger = logging.getLogger(__name__)


class FVGRetestV3(SensorV3):
    @property
    def name(self) -> str:
        return "FVGRetest"

    def __init__(self, min_gap_pct=0.001):
        self.min_gap_pct = min_gap_pct
        self.candles: Dict[str, deque] = {}
        self.active_fvgs: Dict[str, list] = {}

    def _get_state(self, tf: str):
        if tf not in self.candles:
            self.candles[tf] = deque(maxlen=100)
            self.active_fvgs[tf] = []
        return self.candles[tf], self.active_fvgs[tf]

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
        buffer, fvgs = self._get_state(tf)
        buffer.append([candle["open"], candle["high"], candle["low"], candle["close"]])

        if len(buffer) < 4:
            return None

        # Detect new FVGs
        c1, c3 = buffer[-4], buffer[-2]
        if c1[1] < c3[2]:  # Bullish FVG
            if (c3[2] - c1[1]) / c1[1] > self.min_gap_pct:
                fvgs.append({"type": "bullish", "top": c3[2], "bottom": c1[1], "signaled": False})
        if c1[2] > c3[1]:  # Bearish FVG
            if (c1[2] - c3[1]) / c3[1] > self.min_gap_pct:
                fvgs.append({"type": "bearish", "top": c1[2], "bottom": c3[1], "signaled": False})

        if len(fvgs) > 5:
            fvgs.pop(0)

        for fvg in fvgs:
            if fvg.get("signaled"):
                continue
            if fvg["type"] == "bullish" and fvg["bottom"] <= candle["low"] <= fvg["top"]:
                fvg["signaled"] = True
                return {"side": "LONG", "score": 1.0, "timeframe": tf, "metadata": {"fvg_type": "bullish"}}
            if fvg["type"] == "bearish" and fvg["bottom"] <= candle["high"] <= fvg["top"]:
                fvg["signaled"] = True
                return {"side": "SHORT", "score": 1.0, "timeframe": tf, "metadata": {"fvg_type": "bearish"}}
        return None
