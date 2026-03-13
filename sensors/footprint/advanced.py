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
from sensors.quant.volatility_regime import RollingZScore


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

        # Scenario 1: Bullish Rejection (Test Support)
        # Price came down to Prev POC and bounced up
        if curr_low <= prev_poc <= curr_open:  # Touched POC from above
            if curr_close > prev_poc:  # Closed above
                # Validation: Wick size
                wick = min(curr_open, curr_close) - curr_low
                body = abs(curr_close - curr_open)
                if wick > body * 0.3:  # Significant rejection wick
                    signal = "LONG"

        # Scenario 2: Bearish Rejection (Test Resistance)
        # Price went up to Prev POC and rejected down
        if curr_high >= prev_poc >= curr_open:  # Touched POC from below
            if curr_close < prev_poc:  # Closed below
                wick = curr_high - max(curr_open, curr_close)
                body = abs(curr_close - curr_open)
                if wick > body * 0.3:
                    signal = "SHORT"

        if signal:
            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalRejection",
                    "direction": signal,
                    "pattern": "POC_Rejection",
                    "poc_level": prev_poc,
                    "rejection_price": curr_close,
                },
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

        # Bearish Divergence: Price Higher, Delta Lower (or Negative)
        # Price made a higher high (or close), but Delta is weaker
        if p1 > p2:  # Uptrend in price
            if d1 < d2:  # Downtrend in momentum (Delta)
                # Stronger if d1 is negative
                signal = "SHORT"

        # Bullish Divergence: Price Lower, Delta Higher (or Positive)
        elif p1 < p2:  # Downtrend in price
            if d1 > d2:  # Uptrend in momentum
                signal = "LONG"

        if signal:
            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalDivergence",
                    "direction": signal,
                    "pattern": "Delta_Divergence",
                    "price_change": p1 - p2,
                    "delta_change": d1 - d2,
                },
            }
        return None


class FootprintStackedImbalance(SensorV3):
    """
    Detects Stacked Imbalances (3+ consecutive levels with imbalance).

    Enhanced to detect:
    1. Initial stacked imbalance (trend direction)
    2. Continuation after pullback (high win rate setup)

    Trader Dale: "Stacked imbalances show institutional footprints.
    When price pulls back to the stack and bounces, it's a continuation signal."
    """

    @property
    def name(self) -> str:
        return "FootprintStackedImbalance"

    def __init__(self, engine=None):
        self.timeframe = "1m"
        self.imbalance_ratio = 3.0  # Fallback
        self.min_stack_size = 3  # Minimum consecutive levels
        self.pullback_pct = 0.38  # Fibonacci 38% pullback threshold
        self.history = deque(maxlen=10)  # Track recent stacks for continuation
        self.ratio_zscore = RollingZScore(window_size=200)
        self.min_zscore_anomaly = 3.0

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        candle = context.get(self.timeframe)
        if not candle:
            return None

        profile = candle.get("profile")
        if not profile:
            return None

        # Helper to get attr
        def get_val(obj, key):
            return getattr(obj, key) if hasattr(obj, key) else obj.get(key)

        curr_high = get_val(candle, "high")
        curr_low = get_val(candle, "low")
        curr_close = get_val(candle, "close")

        # Sort levels by price
        sorted_levels = sorted(profile.items(), key=lambda x: float(x[0]))

        # Check for Bid Stack (Aggressive Selling)
        bid_stack = self._find_stack(sorted_levels, "bid", "ask")

        # Check for Ask Stack (Aggressive Buying)
        ask_stack = self._find_stack(sorted_levels, "ask", "bid")

        # Store stack info for continuation detection
        if bid_stack:
            self.history.append(
                {
                    "type": "BID_STACK",
                    "levels": bid_stack["levels"],
                    "high": curr_high,
                    "low": curr_low,
                    "time": get_val(candle, "timestamp"),
                }
            )
            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalStackedImbalance",
                    "direction": "SHORT",
                    "pattern": "Stacked_Imbalance_Bid",
                    "levels": bid_stack["levels"],
                    "count": bid_stack["count"],
                },
            }

        if ask_stack:
            self.history.append(
                {
                    "type": "ASK_STACK",
                    "levels": ask_stack["levels"],
                    "high": curr_high,
                    "low": curr_low,
                    "time": get_val(candle, "timestamp"),
                }
            )
            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalStackedImbalance",
                    "direction": "LONG",
                    "pattern": "Stacked_Imbalance_Ask",
                    "levels": ask_stack["levels"],
                    "count": ask_stack["count"],
                },
            }

        # No new stack - check for continuation after pullback
        continuation = self._check_continuation(candle, curr_high, curr_low, curr_close)
        if continuation:
            return continuation

        return None

    def _find_stack(self, sorted_levels: list, aggressive_key: str, passive_key: str) -> Optional[Dict]:
        """Find stacked imbalance in profile."""
        stack_count = 0
        stack_levels = []

        for price, vol in sorted_levels:
            agg_vol = vol[aggressive_key]
            pas_vol = vol[passive_key]

            # Avoid division by zero
            if pas_vol == 0:
                ratio = agg_vol if agg_vol > 0 else 0
            else:
                ratio = agg_vol / pas_vol

            is_stacked_imbalance = False
            if agg_vol > 1.0:
                self.ratio_zscore.update(ratio)
                if self.ratio_zscore.is_ready:
                    z = self.ratio_zscore.get_zscore(ratio)
                    if z >= self.min_zscore_anomaly:
                        is_stacked_imbalance = True
                elif ratio >= self.imbalance_ratio:
                    is_stacked_imbalance = True

            if is_stacked_imbalance:
                stack_count += 1
                stack_levels.append(float(price))
            else:
                # Reset if sequence breaks
                if stack_count >= self.min_stack_size:
                    break
                stack_count = 0
                stack_levels = []

        if stack_count >= self.min_stack_size:
            return {"count": stack_count, "levels": stack_levels}
        return None

    def _check_continuation(self, candle: dict, curr_high: float, curr_low: float, curr_close: float) -> Optional[Dict]:
        """
        Check for continuation after pullback to previous stack.

        Logic:
        1. Find recent stack in history
        2. Check if price pulled back to stack zone
        3. Check if price is now bouncing (continuation)
        """
        if not self.history:
            return None

        # Look at recent stacks
        for past in list(self.history)[-5:]:
            stack_type = past["type"]
            stack_levels = past["levels"]
            stack_high = max(stack_levels)
            stack_low = min(stack_levels)
            past_high = past["high"]
            past_low = past["low"]

            # Calculate pullback
            if stack_type == "ASK_STACK":
                # Bullish continuation - price pulled back to stack
                # Stack was support, price should bounce
                move_high = past_high - past_low
                if move_high <= 0:
                    continue

                pullback = past_high - curr_low
                pullback_pct = pullback / move_high if move_high > 0 else 0

                # Check if pullback reached stack zone (38-62% retracement)
                if 0.38 <= pullback_pct <= 0.62:
                    # Check if price is bouncing (close > low)
                    if curr_close > curr_low:
                        # Continuation signal
                        return {
                            "side": "TACTICAL",
                            "metadata": {
                                "tactical_type": "TacticalStackedImbalance",
                                "direction": "LONG",
                                "pattern": "Stacked_Imbalance_Continuation",
                                "original_stack": "ASK_STACK",
                                "stack_zone": [stack_low, stack_high],
                                "pullback_pct": round(pullback_pct, 2),
                            },
                        }

            elif stack_type == "BID_STACK":
                # Bearish continuation - price pulled back to stack
                # Stack was resistance, price should drop
                move_low = past_high - past_low
                if move_low <= 0:
                    continue

                pullback = curr_high - past_low
                pullback_pct = pullback / move_low if move_low > 0 else 0

                if 0.38 <= pullback_pct <= 0.62:
                    if curr_close < curr_high:
                        return {
                            "side": "TACTICAL",
                            "metadata": {
                                "tactical_type": "TacticalStackedImbalance",
                                "direction": "SHORT",
                                "pattern": "Stacked_Imbalance_Continuation",
                                "original_stack": "BID_STACK",
                                "stack_zone": [stack_low, stack_high],
                                "pullback_pct": round(pullback_pct, 2),
                            },
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
                        "side": "TACTICAL",
                        "metadata": {
                            "tactical_type": "TacticalTrappedTraders",
                            "direction": "SHORT",
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
                        "side": "TACTICAL",
                        "metadata": {
                            "tactical_type": "TacticalTrappedTraders",
                            "direction": "LONG",
                            "pattern": "Trapped_Sellers",
                            "trap_price": prev_low,
                            "wick_vol_pct": wick_vol / total_vol,
                        },
                    }

        return None
