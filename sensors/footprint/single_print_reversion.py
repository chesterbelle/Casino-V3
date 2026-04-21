"""
TacticalSinglePrintReversion Sensor - LTA V5 (Redesigned)
Detects single print zones (ultra-low volume) and signals when price returns to test them.

Based on Market Profile / Auction Market Theory:
Single prints are price levels with minimal volume where the market moved so fast
that no two-sided trade occurred. They represent "unfinished business" and act
as magnets for future price action.

References:
- NexusFi Academy: Single Prints concept
- Axia Futures: Market Profile methodology
- Shadow Trader: Single prints as support/resistance
"""

import time
from collections import deque
from typing import Any, Dict, Optional

import numpy as np

from sensors.base import SensorV3


class TacticalSinglePrintReversion(SensorV3):
    """
    Detects single print zones at VA edges and signals reversion when price tests them.

    Single Print Definition:
    - Price level with volume in bottom 10th percentile of session
    - Formed during fast directional moves (initiative activity)
    - Represents incomplete auction / unfinished business

    Trading Logic:
    1. Track volume distribution across price levels
    2. Identify single print zones (ultra-low volume) near VAH/VAL
    3. When price returns to test the zone, signal reversion if it bounces

    Pattern:
    - Price creates single print at VAH (fast move up, thin volume)
    - Price pulls back to test the single print zone
    - If price bounces (rejection), signal SHORT reversion
    - Vice versa for VAL
    """

    def __init__(self):
        super().__init__()
        self.timeframe = "1m"

        # Volume distribution tracking per price level
        # {price_level: total_volume}
        self.volume_by_price = {}
        self.price_levels_history = deque(maxlen=100)  # Last 100 candles

        # Single print zones tracking
        # {price: {"volume": float, "timestamp": float, "type": "high"|"low"}}
        self.single_print_zones = {}

        # Session tracking
        self.session_high = 0.0
        self.session_low = float("inf")
        self.session_start_ts = 0.0

        # Cooldown
        self.last_signal_ts = 0.0
        self.signal_cooldown = 30.0

        # Configuration
        self.single_print_percentile = 10  # Bottom 10th percentile = single print
        self.proximity_threshold = 0.0025  # 0.25% proximity to VA edge
        self.bounce_threshold = 0.0015  # 0.15% bounce to confirm rejection

    @property
    def name(self) -> str:
        return "TacticalSinglePrintReversion"

    def calculate(self, context: Dict[str, Any]) -> Optional[Dict]:
        """Main calculation on each 1m candle."""
        candle = context.get(self.timeframe)
        if not candle:
            return None

        # Extract candle data
        high = float(candle.get("high", 0))
        low = float(candle.get("low", 0))
        close = float(candle.get("close", 0))
        volume = float(candle.get("volume", 0))
        timestamp = float(candle.get("timestamp", time.time()))

        # Get structural levels
        poc = float(candle.get("poc", 0))
        vah = float(candle.get("vah", 0))
        val = float(candle.get("val", 0))

        if high <= 0 or low <= 0 or volume <= 0:
            return None

        if poc <= 0 or vah <= 0 or val <= 0:
            return None

        # Check cooldown
        if timestamp - self.last_signal_ts < self.signal_cooldown:
            return None

        # Reset session tracking if needed (24h)
        if timestamp - self.session_start_ts > 86400:
            self._reset_session(timestamp)

        # Update volume distribution
        self._update_volume_distribution(high, low, close, volume)

        # Update session extremes and identify single prints
        if high > self.session_high:
            self.session_high = high
            self._check_for_single_print(high, volume, timestamp, "high", vah)

        if low < self.session_low:
            self.session_low = low
            self._check_for_single_print(low, volume, timestamp, "low", val)

        # Check if price is testing a single print zone
        signal = self._check_single_print_test(close, high, low, vah, val, timestamp)

        if signal:
            self.last_signal_ts = timestamp
            return signal

        return None

    def _update_volume_distribution(self, high: float, low: float, close: float, volume: float):
        """Update volume distribution across price levels."""
        # Distribute volume across the candle range
        # Simple approach: assign volume to close price primarily
        price_key = round(close, 2)  # Round to 2 decimals for grouping

        if price_key not in self.volume_by_price:
            self.volume_by_price[price_key] = 0.0

        self.volume_by_price[price_key] += volume

        # Track price levels for percentile calculation
        self.price_levels_history.append({"price": close, "volume": volume, "high": high, "low": low})

        # Cleanup old price levels (keep only recent session)
        if len(self.volume_by_price) > 500:
            # Remove oldest 20% of entries
            sorted_by_time = sorted(self.price_levels_history, key=lambda x: x.get("timestamp", 0))
            cutoff_idx = len(sorted_by_time) // 5
            for entry in sorted_by_time[:cutoff_idx]:
                price_key = round(entry["price"], 2)
                if price_key in self.volume_by_price:
                    del self.volume_by_price[price_key]

    def _check_for_single_print(self, price: float, volume: float, timestamp: float, extreme_type: str, va_edge: float):
        """Check if this extreme qualifies as a single print zone."""
        # Need minimum history
        if len(self.price_levels_history) < 20:
            return

        # Calculate volume percentile
        volumes = [entry["volume"] for entry in self.price_levels_history]
        percentile_threshold = np.percentile(volumes, self.single_print_percentile)

        # Check if volume is in bottom percentile (single print)
        if volume > percentile_threshold:
            return  # Not a single print

        # Check if near VA edge
        if va_edge <= 0:
            return

        distance_pct = abs(price - va_edge) / va_edge
        if distance_pct > self.proximity_threshold:
            return  # Not at VA edge

        # This is a single print zone
        price_key = round(price, 2)
        self.single_print_zones[price_key] = {
            "volume": volume,
            "timestamp": timestamp,
            "type": extreme_type,
            "va_edge": va_edge,
            "percentile": (volume / percentile_threshold) * 100 if percentile_threshold > 0 else 0,
        }

        # Keep only recent single prints (last 50)
        if len(self.single_print_zones) > 50:
            oldest_key = min(
                self.single_print_zones.keys(),
                key=lambda k: self.single_print_zones[k]["timestamp"],
            )
            del self.single_print_zones[oldest_key]

    def _check_single_print_test(
        self,
        close: float,
        high: float,
        low: float,
        vah: float,
        val: float,
        timestamp: float,
    ) -> Optional[Dict]:
        """Check if price is testing a single print zone and bouncing."""
        if not self.single_print_zones:
            return None

        # Check each single print zone
        for price_key, zone_data in list(self.single_print_zones.items()):
            zone_price = price_key
            zone_type = zone_data["type"]
            zone_ts = zone_data["timestamp"]

            # Skip very old zones (>4 hours)
            if timestamp - zone_ts > 14400:
                continue

            # Check if price is testing the zone
            distance_to_zone = abs(close - zone_price) / close

            if distance_to_zone > 0.005:  # Not close enough (0.5%)
                continue

            # Determine if this is a bounce (rejection)
            if zone_type == "high":
                # Single print at high (VAH area)
                # Looking for SHORT signal: price tested high and bounced down
                if high >= zone_price * 0.999:  # Touched the zone
                    bounce_distance = (high - close) / high
                    if bounce_distance >= self.bounce_threshold:
                        # Price bounced down from single print zone
                        return {
                            "side": "TACTICAL",
                            "metadata": {
                                "tactical_type": "TacticalSinglePrintReversion",
                                "direction": "SHORT",
                                "pattern": "Single_Print_Rejection_High",
                                "price": close,
                                "single_print_price": zone_price,
                                "single_print_volume": zone_data["volume"],
                                "single_print_age_minutes": (timestamp - zone_ts) / 60,
                                "bounce_pct": round(bounce_distance * 100, 3),
                                "vah": vah,
                                "val": val,
                                "poc": (vah + val) / 2,  # Approximate
                                "high": high,
                                "low": low,
                                "close": close,
                            },
                        }

            elif zone_type == "low":
                # Single print at low (VAL area)
                # Looking for LONG signal: price tested low and bounced up
                if low <= zone_price * 1.001:  # Touched the zone
                    bounce_distance = (close - low) / low
                    if bounce_distance >= self.bounce_threshold:
                        # Price bounced up from single print zone
                        return {
                            "side": "TACTICAL",
                            "metadata": {
                                "tactical_type": "TacticalSinglePrintReversion",
                                "direction": "LONG",
                                "pattern": "Single_Print_Rejection_Low",
                                "price": close,
                                "single_print_price": zone_price,
                                "single_print_volume": zone_data["volume"],
                                "single_print_age_minutes": (timestamp - zone_ts) / 60,
                                "bounce_pct": round(bounce_distance * 100, 3),
                                "vah": vah,
                                "val": val,
                                "poc": (vah + val) / 2,  # Approximate
                                "high": high,
                                "low": low,
                                "close": close,
                            },
                        }

        return None

    def _reset_session(self, timestamp: float):
        """Reset session tracking."""
        self.session_high = 0.0
        self.session_low = float("inf")
        self.session_start_ts = timestamp
        self.volume_by_price.clear()
        self.single_print_zones.clear()
        self.price_levels_history.clear()
