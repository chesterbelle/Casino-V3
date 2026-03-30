"""
Liquidity Windows Value Area Sensor.

Adapts James Dalton's Market Profile concepts for crypto 24/7 markets.
Uses fixed UTC liquidity windows instead of traditional session boundaries.

Liquidity Windows:
- Asian: 00:00-08:00 UTC (Lower volatility, range-bound)
- London: 08:00-16:00 UTC (Higher volatility, trend potential)
- NY: 13:00-21:00 UTC (Highest volatility during overlap)
- London-NY Overlap: 13:00-16:00 UTC (Peak liquidity)
- Quiet: 21:00-00:00 UTC (Low liquidity, avoid trading)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3

logger = logging.getLogger(__name__)


# =============================================================================
# LIQUIDITY WINDOWS CONFIGURATION
# =============================================================================

LIQUIDITY_WINDOWS = {
    "asian": {
        "start_hour": 0,
        "end_hour": 8,
        "ib_duration_minutes": 10,  # IB = first 10 min (HFT scalping)
        "volatility": "low",
        "description": "Asian Session - Lower volatility, range-bound",
    },
    "london": {
        "start_hour": 8,
        "end_hour": 16,
        "ib_duration_minutes": 10,  # IB = first 10 min (HFT scalping)
        "volatility": "medium_high",
        "description": "London Session - Higher volatility, trend potential",
    },
    "ny": {
        "start_hour": 13,
        "end_hour": 21,
        "ib_duration_minutes": 10,  # IB = first 10 min (HFT scalping)
        "volatility": "high",
        "description": "NY Session - Highest volatility",
    },
    "overlap": {
        "start_hour": 13,
        "end_hour": 16,
        "ib_duration_minutes": 5,  # IB = first 5 min (peak liquidity, faster)
        "volatility": "very_high",
        "description": "London-NY Overlap - Peak liquidity, best scalping",
    },
    "quiet": {
        "start_hour": 21,
        "end_hour": 24,  # 24 = 00:00 next day
        "ib_duration_minutes": 10,
        "volatility": "very_low",
        "description": "Quiet Hours - Low liquidity, avoid trading",
    },
}

# Window type thresholds (adapted from Dalton's Day Type)
# Extension = how far price moved beyond IB as percentage of IB range
WINDOW_TYPE_THRESHOLDS = {
    "trend": 1.0,  # > 100% extension = TREND_WINDOW
    "normal": 0.2,  # 20-100% extension = NORMAL_WINDOW
    # < 20% extension = RANGE_WINDOW
}


# =============================================================================
# WINDOW STATE CLASS
# =============================================================================


class WindowState:
    """Tracks state for a single liquidity window."""

    def __init__(self, window_name: str, config: dict, tick_size: float):
        self.window_name = window_name
        self.config = config
        self.tick_size = tick_size

        # Market Profile for this window
        self.market_profile = MarketProfile(tick_size=tick_size)

        # Initial Balance
        self.ib_duration_minutes = config["ib_duration_minutes"]
        self.ib_candle_count = 0  # 1-min candles
        self.ib_high = -float("inf")
        self.ib_low = float("inf")
        self.ib_defined = False

        # Window range tracking
        self.window_high = -float("inf")
        self.window_low = float("inf")

        # Window type - default to NORMAL_WINDOW to allow trading from start
        self.window_type = "NORMAL_WINDOW"

    def reset(self):
        """Reset state for new window."""
        self.market_profile.reset()
        self.ib_candle_count = 0
        self.ib_high = -float("inf")
        self.ib_low = float("inf")
        self.ib_defined = False
        self.window_high = -float("inf")
        self.window_low = float("inf")
        self.window_type = "NORMAL_WINDOW"

    def update_ib(self, candle_high: float, candle_low: float):
        """Update Initial Balance during IB period."""
        self.ib_candle_count += 1
        self.ib_high = max(self.ib_high, candle_high)
        self.ib_low = min(self.ib_low, candle_low)

        if self.ib_candle_count >= self.ib_duration_minutes:
            self.ib_defined = True

    def update_range(self, candle_high: float, candle_low: float):
        """Update window range."""
        self.window_high = max(self.window_high, candle_high)
        self.window_low = min(self.window_low, candle_low)

    def classify_window_type(self) -> str:
        """Classify window type based on extension from IB."""
        # If IB not yet defined, keep current type (starts as NORMAL_WINDOW)
        if not self.ib_defined:
            return self.window_type

        ib_range = self.ib_high - self.ib_low
        if ib_range <= 0:
            return self.window_type  # Keep current type instead of DEVELOPING

        # Calculate extension
        extension_up = (self.window_high - self.ib_high) / ib_range
        extension_down = (self.ib_low - self.window_low) / ib_range
        max_extension = max(extension_up, extension_down)

        # Classify
        if max_extension > WINDOW_TYPE_THRESHOLDS["trend"]:
            self.window_type = "TREND_WINDOW"
        elif max_extension > WINDOW_TYPE_THRESHOLDS["normal"]:
            self.window_type = "NORMAL_WINDOW"
        else:
            self.window_type = "RANGE_WINDOW"

        return self.window_type


# =============================================================================
# SESSION VALUE AREA SENSOR (Liquidity Windows Version)
# =============================================================================


class SessionValueArea(SensorV3):
    """
    Liquidity Windows Value Area Sensor.

    Adapts James Dalton's Market Profile concepts for crypto 24/7 markets.
    Uses fixed UTC liquidity windows instead of traditional session boundaries.

    Key Adaptations:
    - "Day Type" → "Window Type" (per liquidity window)
    - "Session" → "Liquidity Window" (Asian/London/NY/Overlap/Quiet)
    - "Opening Range" → "Window IB" (first N minutes of each window)
    - Profile resets on window transition

    Provides:
    - Current liquidity window name
    - Window Type (TREND/NORMAL/RANGE)
    - Value Area levels (POC, VAH, VAL)
    - Initial Balance levels (IB High, IB Low)
    - Excess and Single Print detection
    - MTF alignment data
    """

    def __init__(self, tick_size: float = 0.5):
        super().__init__()
        self.tick_size = tick_size
        self.symbol = "Unknown"

        # Window states (one per liquidity window)
        self.window_states: Dict[str, WindowState] = {}
        for window_name, config in LIQUIDITY_WINDOWS.items():
            self.window_states[window_name] = WindowState(window_name, config, tick_size)

        # Current active window
        self.current_window: Optional[str] = None

        # Last candle timestamp (to detect new candle)
        self.last_candle_ts: Optional[float] = None

    @property
    def name(self) -> str:
        return "SessionValueArea"

    def _get_current_window(self, utc_hour: int) -> str:
        """
        Determine current liquidity window based on UTC hour.

        Priority: Overlap > London > NY > Asian > Quiet
        (Overlap is a subset of both London and NY, check first)
        """
        # Check overlap first (it's a subset of London and NY)
        if 13 <= utc_hour < 16:
            return "overlap"
        # Then NY (13-21, but overlap already handled)
        if 16 <= utc_hour < 21:
            return "ny"
        # Then London (8-16, but overlap already handled)
        if 8 <= utc_hour < 13:
            return "london"
        # Then Asian
        if 0 <= utc_hour < 8:
            return "asian"
        # Quiet hours (21-24)
        return "quiet"

    def _is_in_ib_period(self, window_name: str) -> bool:
        """Check if current time is within IB period of the window."""
        window_state = self.window_states.get(window_name)
        if not window_state:
            return False
        return not window_state.ib_defined

    def is_at_key_level(self, price: float, proximity_ticks: int = 4) -> dict:
        """
        Check if price is near a key level (POC, VAH, VAL, IB High, IB Low).

        This is the Level Context Filter from the strategy - signals should only
        be taken when price is at a key level.

        Args:
            price: Current price to check
            proximity_ticks: Number of ticks to consider "at level"

        Returns:
            dict with 'at_level' (bool), 'level_type' (str), 'level_price' (float)
        """
        if self.current_window is None:
            return {"at_level": False, "level_type": None, "level_price": None}

        window_state = self.window_states[self.current_window]
        prox = proximity_ticks * self.tick_size

        # Get key levels
        poc, vah, val = window_state.market_profile.calculate_value_area()

        # Check Value Area levels
        if poc > 0 and abs(price - poc) <= prox:
            return {"at_level": True, "level_type": "POC", "level_price": poc}
        if vah > 0 and abs(price - vah) <= prox:
            return {"at_level": True, "level_type": "VAH", "level_price": vah}
        if val > 0 and abs(price - val) <= prox:
            return {"at_level": True, "level_type": "VAL", "level_price": val}

        # Check IB levels if defined
        if window_state.ib_defined:
            if abs(price - window_state.ib_high) <= prox:
                return {"at_level": True, "level_type": "IB_HIGH", "level_price": window_state.ib_high}
            if abs(price - window_state.ib_low) <= prox:
                return {"at_level": True, "level_type": "IB_LOW", "level_price": window_state.ib_low}

        return {"at_level": False, "level_type": None, "level_price": None}

    def get_key_levels(self) -> dict:
        """
        Get all current key levels for reference.

        Returns:
            dict with POC, VAH, VAL, IB_HIGH, IB_LOW
        """
        if self.current_window is None:
            return {}

        window_state = self.window_states[self.current_window]
        poc, vah, val = window_state.market_profile.calculate_value_area()

        return {
            "poc": poc,
            "vah": vah,
            "val": val,
            "ib_high": window_state.ib_high if window_state.ib_defined else None,
            "ib_low": window_state.ib_low if window_state.ib_defined else None,
            "ib_defined": window_state.ib_defined,
        }

    def calculate(self, context: Dict[str, Optional[dict]]) -> Optional[dict]:
        candle = context.get("1m")
        if not candle:
            return None

        self.symbol = candle.get("symbol", "Unknown")

        # Determine current liquidity window from UTC time
        # Use candle timestamp if available, else current time
        candle_ts = candle.get("timestamp")
        if candle_ts:
            # timestamp is Unix epoch, convert to UTC hour
            utc_dt = datetime.fromtimestamp(candle_ts, tz=timezone.utc)
            utc_hour = utc_dt.hour
        else:
            utc_hour = datetime.now(timezone.utc).hour

        new_window = self._get_current_window(utc_hour)

        # Check for window transition
        if self.current_window != new_window:
            logger.info(
                f"🔄 [LiquidityWindow] Transition: {self.current_window} → {new_window} " f"(UTC {utc_hour:02d}:00)"
            )
            # Reset the new window state
            self.window_states[new_window].reset()
            self.current_window = new_window

        # Get current window state
        window_state = self.window_states[self.current_window]

        # Update Market Profile with candle's profile data
        profile = candle.get("profile")
        if profile:
            for price_str, vols in profile.items():
                price = float(price_str)
                vol = float(vols.get("bid", 0) + vols.get("ask", 0))
                window_state.market_profile.add_trade(price, vol)

        # Update window range
        window_state.update_range(candle["high"], candle["low"])

        # Update Initial Balance if in IB period
        if self._is_in_ib_period(self.current_window):
            window_state.update_ib(candle["high"], candle["low"])
            if window_state.ib_defined:
                logger.info(
                    f"🏛️ [IB] Initial Balance defined for {self.current_window.upper()}: "
                    f"{window_state.ib_low} - {window_state.ib_high}"
                )

        # Classify window type
        window_type = window_state.classify_window_type()

        # Calculate Value Area levels
        poc, vah, val = window_state.market_profile.calculate_value_area()

        # Determine price position relative to VA and IB
        price = candle["close"]
        position = "INSIDE_VA"
        if price > vah:
            position = "ABOVE_VA"
        elif price < val:
            position = "BELOW_VA"

        ib_position = "INSIDE_IB"
        if window_state.ib_defined:
            if price > window_state.ib_high:
                ib_position = "IB_BREAKOUT_UP"
            elif price < window_state.ib_low:
                ib_position = "IB_BREAKOUT_DOWN"

        # Excess and Single Print detection
        single_prints = []
        excess_high = False
        excess_low = False
        failed_auctions = []  # Phase 800: Incomplete Business

        if window_state.market_profile.total_volume > 0:
            avg_vol_per_level = window_state.market_profile.total_volume / len(window_state.market_profile.profile)
            sorted_prices = sorted(window_state.market_profile.profile.keys())

            # 1. Single Prints
            for p in sorted_prices:
                if window_state.market_profile.profile[p] < (avg_vol_per_level * 0.1):
                    single_prints.append(p)

            # 2. Excess at extremes (Dalton Tails)
            if len(sorted_prices) > 10:
                high_lvl = sorted_prices[-1]
                low_lvl = sorted_prices[0]

                if window_state.market_profile.profile[high_lvl] > avg_vol_per_level * 1.5 and price < vah:
                    excess_high = True
                if window_state.market_profile.profile[low_lvl] > avg_vol_per_level * 1.5 and price > val:
                    excess_low = True

            # 3. Failed Auctions (Incomplete Business) - Phase 800
            # Look at the 1m candle profile specifically for this bar
            bar_p_data = candle.get("profile", {})
            bar_vol = candle.get("volume", 1)
            if bar_p_data:
                bar_prices = sorted([float(p) for p in bar_p_data.keys()])
                if bar_prices:
                    high_p = bar_prices[-1]
                    low_p = bar_prices[0]
                    # Failed High: Significant Ask at High, price closed lower
                    high_data = bar_p_data.get(str(high_p), {})
                    high_ask = float(high_data.get("ask", 0))
                    if high_ask > (bar_vol * 0.05) and price < high_p:
                        failed_auctions.append({"price": high_p, "type": "FAILED_HIGH", "vol": high_ask})
                        logger.info(f"🎯 [FAILED_AUCTION] HIGH detected at {high_p} (Ask: {high_ask})")

                    # Failed Low: Significant Bid at Low, price closed higher
                    low_data = bar_p_data.get(str(low_p), {})
                    low_bid = float(low_data.get("bid", 0))
                    if low_bid > (bar_vol * 0.05) and price > low_p:
                        failed_auctions.append({"price": low_p, "type": "FAILED_LOW", "vol": low_bid})
                        logger.info(f"🎯 [FAILED_AUCTION] LOW detected at {low_p} (Bid: {low_bid})")

        # MTF Alignment Data
        mtf_30m_poc = None
        mtf_30m_side = "NEUTRAL"
        mtf_30m = context.get("30m")
        if mtf_30m and mtf_30m.get("poc"):
            mtf_30m_poc = mtf_30m["poc"]
            if mtf_30m["close"] > mtf_30m_poc:
                mtf_30m_side = "BULLISH"
            elif mtf_30m["close"] < mtf_30m_poc:
                mtf_30m_side = "BEARISH"

        # Log window state
        logger.debug(
            f"📊 [WindowContext] {self.current_window.upper()} | "
            f"Type: {window_type} | POC: {poc} | VA: [{val}, {vah}] | "
            f"IB: [{window_state.ib_low}, {window_state.ib_high}] | "
            f"IB_Defined: {window_state.ib_defined}"
        )

        return {
            "side": "NEUTRAL",  # Context sensor
            "score": 0.5,
            "metadata": {
                "type": "LiquidityWindow_Context",
                # Window info
                "liquidity_window": self.current_window,
                "window_type": window_type,
                "window_volatility": LIQUIDITY_WINDOWS[self.current_window]["volatility"],
                # Value Area
                "poc": poc,
                "vah": vah,
                "val": val,
                # Initial Balance
                "ib_high": window_state.ib_high if window_state.ib_defined else None,
                "ib_low": window_state.ib_low if window_state.ib_defined else None,
                "ib_defined": window_state.ib_defined,
                "ib_candle_count": window_state.ib_candle_count,
                # Position
                "position": position,
                "ib_position": ib_position,
                # Excess/Single Prints
                "excess": {"high": excess_high, "low": excess_low},
                "single_print_count": len(single_prints),
                "failed_auctions": failed_auctions,  # Phase 800
                "vol_total": window_state.market_profile.total_volume,
                # MTF
                "mtf_30m_poc": mtf_30m_poc,
                "mtf_30m_side": mtf_30m_side,
                # Legacy compatibility (for aggregator)
                "day_type": window_type,  # Map window_type to day_type for backward compat
            },
        }
