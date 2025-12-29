from collections import deque
from typing import Any, Dict, Optional

from sensors.base import SensorV3


class FootprintDeltaPoCShift(SensorV3):
    """
    Footprint Delta/PoC Shift Sensor.

    Detects strong impulse:
    1. Delta is strong (Positive for Long, Negative for Short).
    2. PoC (Point of Control) shifts in the direction of the trend.
    3. Price closes near the extreme.
    """

    def __init__(self):
        self.history = deque(maxlen=5)

    @property
    def name(self) -> str:
        return "FootprintDeltaPoCShift"

    def calculate(self, context: Dict[str, Any]) -> Optional[dict]:
        candle = context.get("1m")
        if not candle:
            return None

        self.history.append(candle)
        if len(self.history) < 2:
            return None

        curr = self.history[-1]
        prev = self.history[-2]

        # Helper
        def get_val(obj, key):
            return getattr(obj, key) if hasattr(obj, key) else obj.get(key)

        curr_poc = get_val(curr, "poc")
        prev_poc = get_val(prev, "poc")
        delta = get_val(curr, "delta")
        close = get_val(curr, "close")
        open_price = get_val(curr, "open")

        if not curr_poc or not prev_poc:
            return None

        # Bullish Shift
        # 1. PoC moved UP
        # 2. Delta is Positive
        # 3. Green Candle
        if curr_poc > prev_poc and delta > 0 and close > open_price:
            return {
                "side": "LONG",
                "score": 0.8,
                "metadata": {"type": "PoC_Shift_Up", "poc_change": curr_poc - prev_poc, "delta": delta},
            }

        # Bearish Shift
        # 1. PoC moved DOWN
        # 2. Delta is Negative
        # 3. Red Candle
        if curr_poc < prev_poc and delta < 0 and close < open_price:
            return {
                "side": "SHORT",
                "score": 0.8,
                "metadata": {"type": "PoC_Shift_Down", "poc_change": curr_poc - prev_poc, "delta": delta},
            }

        return None
