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

        profile = candle.get("profile")
        if not profile:
            return None

        # Prices in the profile are usually strings because of JSON, or floats
        # Let's ensure they are sorted floats
        prices = sorted([float(p) for p in profile.keys()])
        if len(prices) < 3:
            return None

        # 1. Calculate Average Volume per level for the "Exhaustion" filter
        # LTA defining exhaustion: extreme level volume < average volume * threshold
        total_vol = 0
        level_count = 0
        for p_str, vols in profile.items():
            level_vol = vols.get("bid", 0) + vols.get("ask", 0)
            total_vol += level_vol
            level_count += 1

        if level_count == 0:
            return None
        avg_vol = total_vol / level_count

        # 2. Check for Bullish Exhaustion (at the Low)
        # Condition: Price at Low + Very Low Ask Volume (Sellers disappeared)
        # Fix: Use tolerance-based key lookup to handle string/float mismatch
        low_price_key = next((k for k in profile if abs(float(k) - prices[0]) < 0.0001), None)
        if not low_price_key:
            return None
        low_vols = profile[low_price_key]
        low_ask = low_vols.get("ask", 0.0)
        low_bid = low_vols.get("bid", 0.0)
        low_total = low_ask + low_bid

        if low_total < (avg_vol * self.volume_threshold):
            # Bullish Exhaustion: No one wants to SELL at the bottom
            # We look for a "Finished Auction" at the bottom where Ask is 0 or tiny
            if low_ask <= (low_bid * 0.1) or low_ask < 1.0:
                return {
                    "side": "TACTICAL",
                    "metadata": {
                        "tactical_type": "TacticalExhaustion",
                        "direction": "LONG",
                        "subtype": "Footprint_Exhaustion_Low",
                        "ratio": round(low_total / avg_vol, 2),
                        "low_ask": low_ask,
                        "low_bid": low_bid,
                        "price": prices[0],
                    },
                }

        # 3. Check for Bearish Exhaustion (at the High)
        # Condition: Price at High + Very Low Bid Volume (Buyers disappeared)
        # Fix: Use tolerance-based key lookup to handle string/float mismatch
        high_price_key = next((k for k in profile if abs(float(k) - prices[-1]) < 0.0001), None)
        if not high_price_key:
            return None
        high_vols = profile[high_price_key]
        high_bid = high_vols.get("bid", 0.0)
        high_ask = high_vols.get("ask", 0.0)
        high_total = high_bid + high_ask

        if high_total < (avg_vol * self.volume_threshold):
            # Bearish Exhaustion: No one wants to BUY at the top
            # Finished Auction at top where Bid is 0 or tiny
            if high_bid <= (high_ask * 0.1) or high_bid < 1.0:
                return {
                    "side": "TACTICAL",
                    "metadata": {
                        "tactical_type": "TacticalExhaustion",
                        "direction": "SHORT",
                        "subtype": "Footprint_Exhaustion_High",
                        "ratio": round(high_total / avg_vol, 2),
                        "high_bid": high_bid,
                        "high_ask": high_ask,
                        "price": prices[-1],
                    },
                }

        return None
