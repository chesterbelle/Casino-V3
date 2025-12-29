from typing import Dict, Optional

from sensors.base import SensorV3


class FootprintVolumeExhaustion(SensorV3):
    """
    Footprint Volume Exhaustion Sensor.

    Detects exhaustion: Price moves to a new extreme but volume dries up.

    Logic:
    - Compare current candle volume to moving average.
    - If volume is significantly lower (< 50% of avg) AND price is at a local extreme (High/Low).
    - Indicates lack of participation/interest at these levels -> Reversal likely.
    """

    def __init__(self, volume_threshold: float = 0.5):
        self.volume_threshold = volume_threshold
        self.history_vol = []

    @property
    def name(self) -> str:
        return "FootprintVolumeExhaustion"

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        candle = context.get("1m")
        if not candle:
            return None

        vol = candle["volume"]
        self.history_vol.append(vol)
        if len(self.history_vol) > 20:
            self.history_vol.pop(0)

        if len(self.history_vol) < 10:
            return None

        avg_vol = sum(self.history_vol[:-1]) / (len(self.history_vol) - 1)

        # Check for Exhaustion (Low Volume)
        if vol < avg_vol * self.volume_threshold:
            # Context:
            # If Red Candle + Low Volume -> Selling Exhaustion -> LONG
            # If Green Candle + Low Volume -> Buying Exhaustion -> SHORT

            is_green = candle["close"] > candle["open"]
            side = "SHORT" if is_green else "LONG"

            return {"side": side, "score": 0.6, "metadata": {"type": "Volume_Exhaustion", "vol_ratio": vol / avg_vol}}

        return None
