import logging
from typing import Dict, Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3

logger = logging.getLogger(__name__)


class SessionValueArea(SensorV3):
    """
    Session-wide Volume Profile and Initial Balance tracker.
    Implements James Dalton's concepts for structural context.

    Tracks:
    - Session-wide POC, VAH, VAL.
    - Initial Balance (High/Low of the first N candles).
    - Day Type (Transitioning from range to trend).
    """

    def __init__(self, tick_size: float = 0.5, ib_candles: int = 60):
        super().__init__()
        self.market_profile = MarketProfile(tick_size=tick_size)
        self.ib_candles = ib_candles
        self.candle_count = 0
        self.ib_high = -float("inf")
        self.ib_low = float("inf")
        self.ib_defined = False
        self.symbol = "Unknown"

    @property
    def name(self) -> str:
        return "SessionValueArea"

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        candle = context.get("1m")
        if not candle:
            return None

        # 1. Update Market Profile with the candle's profile data
        profile = candle.get("profile")
        if profile:
            for price_str, vols in profile.items():
                price = float(price_str)
                vol = float(vols.get("bid", 0) + vols.get("ask", 0))
                self.market_profile.add_trade(price, vol)

        # 2. Update Initial Balance (IB)
        if not self.ib_defined:
            self.candle_count += 1
            self.ib_high = max(self.ib_high, candle["high"])
            self.ib_low = min(self.ib_low, candle["low"])

            if self.candle_count >= self.ib_candles:
                self.ib_defined = True
                logger.info(f"🏛️ [Session] Initial Balance defined for {self.symbol}: {self.ib_low} - {self.ib_high}")

        # 2.5 Gap 3: Day Type Classification
        # Normal Day: Wide IB, little extension
        # Trend Day: Aggressive extension beyond IB
        # Range Day: Price stays within IB
        day_type = "DEVELOPING"
        if self.ib_defined:
            ib_range = self.ib_high - self.ib_low
            # We need session range
            session_high = max(self.ib_high, candle["high"])
            session_low = min(self.ib_low, candle["low"])
            extension_up = (session_high - self.ib_high) / ib_range if ib_range > 0 else 0
            extension_down = (self.ib_low - session_low) / ib_range if ib_range > 0 else 0

            if extension_up > 1.0 or extension_down > 1.0:
                day_type = "TREND_DAY"
            elif extension_up > 0.2 or extension_down > 0.2:
                day_type = "NORMAL_VARIATION"
            else:
                day_type = "RANGE_DAY"

        # 3. Calculate Session Levels
        poc, vah, val = self.market_profile.calculate_value_area()

        # 4. Determine Price Position relative to Value Area and IB
        price = candle["close"]
        position = "INSIDE_VA"
        if price > vah:
            position = "ABOVE_VA"
        elif price < val:
            position = "BELOW_VA"

        ib_position = "INSIDE_IB"
        if self.ib_defined:
            if price > self.ib_high:
                ib_position = "IB_BREAKOUT_UP"
            elif price < self.ib_low:
                ib_position = "IB_BREAKOUT_DOWN"

        # 2.6 Gap 4: Excess and Single Print Detection
        # Excess (Tails): High volume at extremes followed by price moving away
        # Single Prints: Levels with < 10% of average session volume
        single_prints = []
        excess_high = False
        excess_low = False

        if self.market_profile.total_volume > 0:
            avg_vol_per_level = self.market_profile.total_volume / len(self.market_profile.profile)
            sorted_profile_prices = sorted(self.market_profile.profile.keys())

            # Single Prints
            for p in sorted_profile_prices:
                if self.market_profile.profile[p] < (avg_vol_per_level * 0.1):
                    single_prints.append(p)

            # Excess at extremes (Dalton Tails)
            if len(sorted_profile_prices) > 10:
                high_lvl = sorted_profile_prices[-1]
                low_lvl = sorted_profile_prices[0]

                # Excess High: High volume at the tip but price is now below VAH
                if self.market_profile.profile[high_lvl] > avg_vol_per_level * 1.5 and price < vah:
                    excess_high = True
                # Excess Low: High volume at the tip but price is now above VAL
                if self.market_profile.profile[low_lvl] > avg_vol_per_level * 1.5 and price > val:
                    excess_low = True

        # 2.7 Gap 6: Multi-Timeframe Alignment Data
        mtf_30m_poc = None
        mtf_30m_side = "NEUTRAL"
        mtf_30m = context.get("30m")
        if mtf_30m and mtf_30m.get("poc"):
            mtf_30m_poc = mtf_30m["poc"]
            if mtf_30m["close"] > mtf_30m_poc:
                mtf_30m_side = "BULLISH"
            elif mtf_30m["close"] < mtf_30m_poc:
                mtf_30m_side = "BEARISH"

        return {
            "side": "NEUTRAL",  # This is a context sensor
            "score": 0.5,
            "metadata": {
                "type": "Session_Context",
                "day_type": day_type,
                "poc": poc,
                "vah": vah,
                "val": val,
                "ib_high": self.ib_high if self.ib_defined else None,
                "ib_low": self.ib_low if self.ib_defined else None,
                "ib_defined": self.ib_defined,
                "position": position,
                "ib_position": ib_position,
                "excess": {"high": excess_high, "low": excess_low},
                "single_print_count": len(single_prints),
                "vol_total": self.market_profile.total_volume,
                "mtf_30m_poc": mtf_30m_poc,
                "mtf_30m_side": mtf_30m_side,
            },
        }
