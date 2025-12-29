"""
Advanced Footprint Sensors
- FootprintPOCRejection: Detects rejection at previous Point of Control.
- FootprintDeltaDivergence: Detects divergence between Price and Delta.
- FootprintStackedImbalance: Detects consecutive price levels with aggressive imbalance.
- FootprintTrappedTraders: Detects high volume at wicks followed by reversal.
"""

from collections import deque
from typing import Any, Dict, Optional

from sensors.base import SensorV3


class FootprintPOCRejection(SensorV3):
    """
    Detects when price tests a previous POC and rejects it.
    Logic:
    1. Identify POC of previous candle.
    2. Check if current candle High/Low touched that POC level.
    3. Check if current candle closed away from it (Rejection).
    """

    @property
    def name(self) -> str:
        return "FootprintPOCRejection"

    def __init__(self, engine=None):
        self.timeframe = "1m"
        self.history = deque(maxlen=5)

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        candle = context.get(self.timeframe)
        if not candle:
            return None

        self.history.append(candle)

        if len(self.history) < 2:
            return None

        current = self.history[-1]
        prev = self.history[-2]

        # Helper to get attr
        def get_val(obj, key):
            return getattr(obj, key) if hasattr(obj, key) else obj.get(key)

        prev_poc = get_val(prev, "poc")
        curr_open = get_val(current, "open")
        curr_close = get_val(current, "close")
        curr_high = get_val(current, "high")
        curr_low = get_val(current, "low")

        if not prev_poc or prev_poc == 0:
            return None

        signal = None
        score = 0.0

        # Scenario 1: Bullish Rejection (Test Support)
        # Price came down to Prev POC and bounced up
        if curr_low <= prev_poc <= curr_open:  # Touched POC from above
            if curr_close > prev_poc:  # Closed above
                # Validation: Wick size
                wick = min(curr_open, curr_close) - curr_low
                body = abs(curr_close - curr_open)
                if wick > body * 0.3:  # Significant rejection wick
                    signal = "LONG"
                    score = 0.8

        # Scenario 2: Bearish Rejection (Test Resistance)
        # Price went up to Prev POC and rejected down
        if curr_high >= prev_poc >= curr_open:  # Touched POC from below
            if curr_close < prev_poc:  # Closed below
                wick = curr_high - max(curr_open, curr_close)
                body = abs(curr_close - curr_open)
                if wick > body * 0.3:
                    signal = "SHORT"
                    score = 0.8

        if signal:
            return {
                "side": signal,
                "score": score,
                "metadata": {"pattern": "POC_Rejection", "poc_level": prev_poc, "rejection_price": curr_close},
            }
        return None


class FootprintDeltaDivergence(SensorV3):
    """
    Detects divergence between Price Trend and Delta Trend.
    """

    @property
    def name(self) -> str:
        return "FootprintDeltaDivergence"

    def __init__(self, engine=None):
        self.timeframe = "1m"
        self.history = deque(maxlen=5)

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        candle = context.get(self.timeframe)
        if not candle:
            return None

        self.history.append(candle)

        if len(self.history) < 3:
            return None

        # Helper to get attr
        def get_val(obj, key):
            return getattr(obj, key) if hasattr(obj, key) else obj.get(key)

        # Get last 2 candles
        c1 = self.history[-1]  # Current/Last closed
        c2 = self.history[-2]  # Previous

        p1 = get_val(c1, "close")
        p2 = get_val(c2, "close")

        d1 = get_val(c1, "delta")
        d2 = get_val(c2, "delta")

        signal = None
        score = 0.0

        # Bearish Divergence: Price Higher, Delta Lower (or Negative)
        # Price made a higher high (or close), but Delta is weaker
        if p1 > p2:  # Uptrend in price
            if d1 < d2:  # Downtrend in momentum (Delta)
                # Stronger if d1 is negative
                score = 0.6
                if d1 < 0:
                    score = 0.9
                signal = "SHORT"

        # Bullish Divergence: Price Lower, Delta Higher (or Positive)
        elif p1 < p2:  # Downtrend in price
            if d1 > d2:  # Uptrend in momentum
                score = 0.6
                if d1 > 0:
                    score = 0.9
                signal = "LONG"

        if signal:
            return {
                "side": signal,
                "score": score,
                "metadata": {"pattern": "Delta_Divergence", "price_change": p1 - p2, "delta_change": d1 - d2},
            }
        return None


class FootprintStackedImbalance(SensorV3):
    """
    Detects Stacked Imbalances (3+ consecutive levels with imbalance).
    """

    @property
    def name(self) -> str:
        return "FootprintStackedImbalance"

    def __init__(self, engine=None):
        self.timeframe = "1m"
        self.imbalance_ratio = 3.0  # Aggressive side > Passive side * 3
        self.min_stack_size = 3  # Minimum consecutive levels

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        candle = context.get(self.timeframe)
        if not candle:
            return None

        profile = candle.get("profile")
        if not profile:
            return None

        # Sort levels by price
        sorted_levels = sorted(profile.items(), key=lambda x: x[0])

        # Check for Bid Stack (Aggressive Selling)
        # Bid > Ask * Ratio
        bid_stack_count = 0
        bid_stack_levels = []

        for price, vol in sorted_levels:
            bid_vol = vol["bid"]
            ask_vol = vol["ask"]

            # Avoid division by zero
            if ask_vol == 0:
                ratio = bid_vol if bid_vol > 0 else 0
            else:
                ratio = bid_vol / ask_vol

            if ratio >= self.imbalance_ratio and bid_vol > 1.0:  # Min volume filter
                bid_stack_count += 1
                bid_stack_levels.append(price)
            else:
                # Reset if sequence breaks
                if bid_stack_count >= self.min_stack_size:
                    # Found a stack!
                    break
                bid_stack_count = 0
                bid_stack_levels = []

        if bid_stack_count >= self.min_stack_size:
            return {
                "side": "SHORT",
                "score": 0.9,
                "metadata": {"pattern": "Stacked_Imbalance_Bid", "levels": bid_stack_levels, "count": bid_stack_count},
            }

        # Check for Ask Stack (Aggressive Buying)
        # Ask > Bid * Ratio
        ask_stack_count = 0
        ask_stack_levels = []

        for price, vol in sorted_levels:
            bid_vol = vol["bid"]
            ask_vol = vol["ask"]

            if bid_vol == 0:
                ratio = ask_vol if ask_vol > 0 else 0
            else:
                ratio = ask_vol / bid_vol

            if ratio >= self.imbalance_ratio and ask_vol > 1.0:
                ask_stack_count += 1
                ask_stack_levels.append(price)
            else:
                if ask_stack_count >= self.min_stack_size:
                    break
                ask_stack_count = 0
                ask_stack_levels = []

        if ask_stack_count >= self.min_stack_size:
            return {
                "side": "LONG",
                "score": 0.9,
                "metadata": {"pattern": "Stacked_Imbalance_Ask", "levels": ask_stack_levels, "count": ask_stack_count},
            }

        return None


class FootprintTrappedTraders(SensorV3):
    """
    Detects Trapped Traders at extremes.
    High volume at wick, price reverses immediately.
    """

    @property
    def name(self) -> str:
        return "FootprintTrappedTraders"

    def __init__(self, engine=None):
        self.timeframe = "1m"
        self.history = deque(maxlen=5)

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        candle = context.get(self.timeframe)
        if not candle:
            return None

        self.history.append(candle)

        if len(self.history) < 2:
            return None

        # Current candle (confirming the move away)
        curr = self.history[-1]
        # Previous candle (where the trap happened)
        prev = self.history[-2]

        # Helper
        def get_val(obj, key):
            return getattr(obj, key) if hasattr(obj, key) else obj.get(key)

        prev_profile = get_val(prev, "profile")
        if not prev_profile:
            return None

        prev_high = get_val(prev, "high")
        prev_low = get_val(prev, "low")
        prev_close = get_val(prev, "close")
        prev_open = get_val(prev, "open")

        curr_close = get_val(curr, "close")

        # Scenario 1: Trapped Buyers at High (Bearish)
        # 1. Previous candle has a wick at the top.
        # 2. High volume in that top wick (Buying).
        # 3. Price closed below the wick.
        # 4. Current candle continues down.

        # Check for upper wick
        upper_wick_start = max(prev_open, prev_close)
        if prev_high > upper_wick_start:
            # Calculate volume in the wick
            wick_vol = 0
            total_vol = get_val(prev, "volume")

            for price, vol in prev_profile.items():
                if price > upper_wick_start:
                    wick_vol += vol["ask"]  # Aggressive buying trapped

            # If wick volume is significant (e.g., > 20% of total)
            if total_vol > 0 and (wick_vol / total_vol) > 0.20:
                # And current price is moving away (down)
                if curr_close < prev_close:
                    return {
                        "side": "SHORT",
                        "score": 0.85,
                        "metadata": {
                            "pattern": "Trapped_Buyers",
                            "trap_price": prev_high,
                            "wick_vol_pct": wick_vol / total_vol,
                        },
                    }

        # Scenario 2: Trapped Sellers at Low (Bullish)
        lower_wick_end = min(prev_open, prev_close)
        if prev_low < lower_wick_end:
            wick_vol = 0
            total_vol = get_val(prev, "volume")

            for price, vol in prev_profile.items():
                if price < lower_wick_end:
                    wick_vol += vol["bid"]  # Aggressive selling trapped

            if total_vol > 0 and (wick_vol / total_vol) > 0.20:
                if curr_close > prev_close:
                    return {
                        "side": "LONG",
                        "score": 0.85,
                        "metadata": {
                            "pattern": "Trapped_Sellers",
                            "trap_price": prev_low,
                            "wick_vol_pct": wick_vol / total_vol,
                        },
                    }

        return None
