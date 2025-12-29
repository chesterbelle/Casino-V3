from typing import Dict, Optional

from sensors.base import SensorV3


class FootprintAbsorptionV3(SensorV3):
    """
    Footprint Absorption Sensor.

    Detects absorption: High volume traded at a price level but price fails to continue.

    Logic:
    - High Ask Volume at the High of the candle -> Absorption (Sellers absorbing Buyers) -> SHORT signal.
    - High Bid Volume at the Low of the candle -> Absorption (Buyers absorbing Sellers) -> LONG signal.
    """

    def __init__(self, min_volume_ratio: float = 2.0):
        self.min_volume_ratio = min_volume_ratio

    @property
    def name(self) -> str:
        return "FootprintAbsorption"

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        candle = context.get("1m")
        if not candle:
            return None

        profile = candle.get("profile")
        if not profile:
            return None

        high = candle["high"]
        low = candle["low"]
        open_price = candle["open"]
        close_price = candle["close"]
        volume = candle["volume"]
        delta = candle["delta"]

        # Calculate average volume per level for relative comparison
        avg_vol_per_level = volume / len(profile) if len(profile) > 0 else 1.0

        # --- Scenario 1: Absorption at High (Bearish) ---
        # Sellers absorbing Buyers:
        # 1. High Volume at the top (Aggressive buying met with Limit Sells)
        # 2. Negative Delta (or weak positive) despite hitting High?
        #    Actually, Absorption usually means Aggressive Buyers (Positive Delta) got stuck.
        #    So we look for: High Volume + Positive Delta + Price failed to close near High (Wick).

        # Check top levels
        top_vol = profile.get(high, {"bid": 0, "ask": 0})
        # Aggressive buying (Ask volume) is high
        if top_vol["ask"] > avg_vol_per_level * self.min_volume_ratio:
            # But price rejected (Upper Wick)
            upper_wick = high - max(open_price, close_price)
            body = abs(close_price - open_price)

            # Significant wick relative to body or total range
            if upper_wick > body * 0.5:
                # Strong signal if Delta is Positive (Buyers tried but failed)
                # Or if Delta is Negative (Sellers took over immediately)
                return {
                    "side": "SHORT",
                    "score": 0.9,
                    "metadata": {"type": "Absorption_High", "vol": top_vol["ask"], "delta": delta, "wick": upper_wick},
                }

        # --- Scenario 2: Absorption at Low (Bullish) ---
        # Buyers absorbing Sellers:
        # 1. High Volume at the bottom (Aggressive selling met with Limit Buys)
        # 2. Price failed to close near Low (Lower Wick).

        low_vol = profile.get(low, {"bid": 0, "ask": 0})
        # Aggressive selling (Bid volume) is high
        if low_vol["bid"] > avg_vol_per_level * self.min_volume_ratio:
            # But price rejected (Lower Wick)
            lower_wick = min(open_price, close_price) - low
            body = abs(close_price - open_price)

            if lower_wick > body * 0.5:
                return {
                    "side": "LONG",
                    "score": 0.9,
                    "metadata": {"type": "Absorption_Low", "vol": low_vol["bid"], "delta": delta, "wick": lower_wick},
                }

        return None
