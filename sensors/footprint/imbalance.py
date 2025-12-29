from typing import Dict, Optional

from sensors.base import SensorV3


class FootprintImbalanceV3(SensorV3):
    """
    Footprint Imbalance Sensor.

    Detects aggressive buying or selling imbalances at specific price levels.

    Logic:
    - Checks the Volume Profile of the current candle.
    - If Ask Volume > Bid Volume * Ratio (e.g. 3:1) -> Buy Imbalance.
    - If Bid Volume > Ask Volume * Ratio -> Sell Imbalance.
    - Signal is generated if imbalance occurs near the close (pushing price).
    """

    def __init__(self, imbalance_ratio: float = 3.0, min_volume: float = 1.0):
        self.imbalance_ratio = imbalance_ratio
        self.min_volume = min_volume

    @property
    def name(self) -> str:
        return "FootprintImbalance"

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        # We only use 1m candle for now as it contains the synthetic footprint
        candle = context.get("1m")
        if not candle:
            return None

        profile = candle.get("profile")
        if not profile:
            return None

        imbalances = []

        # Analyze each price level
        for price, vol in profile.items():
            bid_vol = vol.get("bid", 0)
            ask_vol = vol.get("ask", 0)

            # Skip low volume levels
            if (bid_vol + ask_vol) < self.min_volume:
                continue

            # Check for Buy Imbalance (Aggressive Buying)
            if ask_vol > bid_vol * self.imbalance_ratio:
                imbalances.append({"side": "LONG", "price": price, "ratio": ask_vol / (bid_vol + 0.1)})

            # Check for Sell Imbalance (Aggressive Selling)
            elif bid_vol > ask_vol * self.imbalance_ratio:
                imbalances.append({"side": "SHORT", "price": price, "ratio": bid_vol / (ask_vol + 0.1)})

        if not imbalances:
            return None

        # Logic: If we have significant imbalances, determine direction
        # For simplicity, we look at the dominant imbalance side
        long_imbalances = [i for i in imbalances if i["side"] == "LONG"]
        short_imbalances = [i for i in imbalances if i["side"] == "SHORT"]

        if len(long_imbalances) > len(short_imbalances):
            return {
                "side": "LONG",
                "score": 1.0,
                "metadata": {"imbalances": len(long_imbalances), "type": "Buy Imbalance"},
            }
        elif len(short_imbalances) > len(long_imbalances):
            return {
                "side": "SHORT",
                "score": 1.0,
                "metadata": {"imbalances": len(short_imbalances), "type": "Sell Imbalance"},
            }

        return None
