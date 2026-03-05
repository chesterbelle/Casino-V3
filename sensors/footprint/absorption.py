"""
Footprint Absorption Sensor - Enhanced with Distributed Zone Detection.

Detects absorption patterns where high volume on both sides occurs but price fails to move:
1. At extremes (High/Low) - Original logic
2. Distributed zones - NEW: Multiple adjacent levels with balanced volume

Trader Dale: "Absorption can be distributed across multiple cells, not just one price level."
"""

import logging
import time
from collections import deque
from typing import Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3
from sensors.footprint.matrix import LiveFootprintMatrix


class FootprintAbsorptionV3(SensorV3):
    """
    Footprint Absorption Sensor.

    Detects absorption: High volume traded at a price level but price fails to continue.

    Enhanced to detect:
    - Absorption at extremes (High/Low)
    - Distributed absorption zones (multiple levels with balanced high volume)
    """

    def __init__(
        self,
        min_volume_ratio: float = 2.0,
        pullback_ticks: int = 5,
        window_seconds: float = 30.0,
        tick_size: float = 0.1,
        level_proximity_ticks: int = 4,
        zone_balance_threshold: float = 0.3,  # Max bid/ask imbalance for zone (30%)
        min_zone_levels: int = 3,  # Minimum levels to form absorption zone
    ):
        super().__init__()
        self.min_volume_ratio = min_volume_ratio
        self.pullback_ticks = pullback_ticks
        self.level_proximity_ticks = level_proximity_ticks
        self.zone_balance_threshold = zone_balance_threshold
        self.min_zone_levels = min_zone_levels
        self.matrix = LiveFootprintMatrix(window_seconds=window_seconds)
        self.market_profile = MarketProfile(tick_size=tick_size)

        # DOM Limit Order Caching
        self.last_best_bid_qty = 0.0
        self.last_best_ask_qty = 0.0
        self.last_best_bid_price = 0.0
        self.last_best_ask_price = 0.0
        self.dom_history = deque(maxlen=100)  # Time-series of DOM state

        # Price movement tracking for zone detection
        self.price_history = deque(maxlen=50)  # Recent prices

        self._last_signal_time = 0.0
        self._signal_cooldown = 2.0  # seconds between signals

    @property
    def name(self) -> str:
        return "FootprintAbsorption"

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        self.matrix.on_tick(tick_data)

        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("qty", 0))
        self.market_profile.add_trade(price, vol)
        self.price_history.append(price)

        now = time.time()
        if now - self._last_signal_time < self._signal_cooldown:
            return None

        profile = self.matrix.profile
        if not profile or len(profile) < 3:
            return None

        current_price = price

        # Find High and Low of the current sliding window
        prices = list(profile.keys())
        high = max(prices)
        low = min(prices)

        # Average volume per level for relative comparison
        total_vol = self.matrix.total_volume
        avg_vol_per_level = total_vol / len(profile)

        # We define a "pullback" as retreating from the extreme by a few price ticks
        prices.sort()
        avg_tick_size = (
            sum(prices[i + 1] - prices[i] for i in range(len(prices) - 1)) / len(prices) if len(prices) > 1 else 0.5
        )

        pullback_distance = avg_tick_size * self.pullback_ticks

        poc, vah, val = self.market_profile.calculate_value_area()

        # Phase 660: Trader Dale Level Filter
        prox = self.level_proximity_ticks * self.market_profile.tick_size
        at_level = (
            abs(current_price - poc) <= prox or abs(current_price - vah) <= prox or abs(current_price - val) <= prox
        )

        # DEBUG: Log state if we are at a level but no signal yet
        if at_level:
            logging.debug(f"🔍 [Absorption Debug] {self.name} at level {current_price} | POC:{poc} VAH:{vah} VAL:{val}")

        signal = None

        # --- Scenario 1: Absorption at High (Bearish) ---
        top_vol = profile.get(high, {"bid": 0.0, "ask": 0.0})
        if top_vol["ask"] > avg_vol_per_level * self.min_volume_ratio:
            if current_price <= high - pullback_distance:
                intensity = top_vol["ask"] / (avg_vol_per_level if avg_vol_per_level > 0 else 1.0)

                wall_confirmed = self._check_dom_wall("ask", high, avg_vol_per_level)

                signal = {
                    "side": "SHORT",
                    "score": 0.9 if wall_confirmed else (0.75 if at_level else 0.4),
                    "metadata": {
                        "type": "Live_Absorption_High",
                        "vol": top_vol["ask"],
                        "fast_track": wall_confirmed and at_level,
                        "absorption_intensity": round(intensity, 2),
                        "dom_wall_confirmed": wall_confirmed,
                        "at_volume_level": at_level,
                        "poc": poc,
                        "vah": vah,
                        "val": val,
                    },
                }

        # --- Scenario 2: Absorption at Low (Bullish) ---
        if not signal:
            low_vol = profile.get(low, {"bid": 0.0, "ask": 0.0})
            if low_vol["bid"] > avg_vol_per_level * self.min_volume_ratio:
                if current_price >= low + pullback_distance:
                    intensity = low_vol["bid"] / (avg_vol_per_level if avg_vol_per_level > 0 else 1.0)

                    wall_confirmed = self._check_dom_wall("bid", low, avg_vol_per_level)

                    signal = {
                        "side": "LONG",
                        "score": 0.9 if wall_confirmed else (0.75 if at_level else 0.4),
                        "metadata": {
                            "type": "Live_Absorption_Low",
                            "vol": low_vol["bid"],
                            "fast_track": wall_confirmed and at_level,
                            "absorption_intensity": round(intensity, 2),
                            "dom_wall_confirmed": wall_confirmed,
                            "at_volume_level": at_level,
                            "poc": poc,
                            "vah": vah,
                            "val": val,
                        },
                    }

        # --- Scenario 3: Distributed Absorption Zone (NEW) ---
        # Multiple adjacent levels with high balanced volume (bid ~ ask)
        # Price stuck in this zone = absorption happening
        if not signal:
            zone_signal = self._detect_absorption_zone(
                profile, current_price, avg_vol_per_level, avg_tick_size, poc, vah, val, at_level
            )
            if zone_signal:
                signal = zone_signal

        if signal:
            self._last_signal_time = now
            return signal

        return None

    def _check_dom_wall(self, side: str, price_level: float, avg_vol: float) -> bool:
        """Check DOM history for a wall at the given price level."""
        for ts, dom in self.dom_history:
            if side == "ask":
                if abs(dom["ask_price"] - price_level) < self.market_profile.tick_size:
                    if dom["ask_qty"] > (avg_vol * 5):
                        return True
            else:  # bid
                if abs(dom["bid_price"] - price_level) < self.market_profile.tick_size:
                    if dom["bid_qty"] > (avg_vol * 5):
                        return True
        return False

    def _detect_absorption_zone(
        self,
        profile: dict,
        current_price: float,
        avg_vol: float,
        tick_size: float,
        poc: float,
        vah: float,
        val: float,
        at_level: bool,
    ) -> Optional[dict]:
        """
        Detect distributed absorption zone.

        Criteria:
        1. Multiple adjacent levels (3+) with high volume
        2. Volume is relatively balanced (bid ~ ask) at each level
        3. Price is oscillating within this zone (not breaking out)
        4. Zone is at a key level
        """
        if avg_vol <= 0:
            return None

        sorted_prices = sorted(profile.keys())

        # Find zones of high-volume balanced levels
        zone_start = None
        zone_levels = []

        for price in sorted_prices:
            vols = profile[price]
            bid_vol = vols.get("bid", 0)
            ask_vol = vols.get("ask", 0)
            total = bid_vol + ask_vol

            # High volume threshold
            if total < avg_vol * self.min_volume_ratio:
                # Zone ended
                if len(zone_levels) >= self.min_zone_levels:
                    break
                zone_levels = []
                zone_start = None
                continue

            # Check balance (bid and ask both significant)
            if total > 0:
                bid_ratio = bid_vol / total
                ask_ratio = ask_vol / total

                # Balanced = neither side dominates
                is_balanced = bid_ratio > self.zone_balance_threshold and ask_ratio > self.zone_balance_threshold

                if is_balanced:
                    if zone_start is None:
                        zone_start = price
                    zone_levels.append(
                        {
                            "price": price,
                            "bid": bid_vol,
                            "ask": ask_vol,
                            "total": total,
                        }
                    )
                else:
                    # Zone broken by imbalance
                    if len(zone_levels) >= self.min_zone_levels:
                        break
                    zone_levels = []
                    zone_start = None

        # Check if we found a valid zone
        if len(zone_levels) < self.min_zone_levels:
            return None

        # Zone boundaries
        zone_high = zone_levels[-1]["price"]
        zone_low = zone_levels[0]["price"]
        zone_mid = (zone_high + zone_low) / 2

        # Check if current price is inside or near the zone
        price_in_zone = zone_low - tick_size <= current_price <= zone_high + tick_size

        if not price_in_zone:
            return None

        # Check if zone is at a key level
        prox = self.level_proximity_ticks * self.market_profile.tick_size
        zone_at_key_level = abs(zone_mid - poc) <= prox or abs(zone_mid - vah) <= prox or abs(zone_mid - val) <= prox

        if not zone_at_key_level:
            return None

        # Calculate zone intensity
        zone_total_vol = sum(lvl["total"] for lvl in zone_levels)
        zone_intensity = zone_total_vol / (avg_vol * len(zone_levels))

        # Determine signal direction based on price position in zone
        # If price near zone high and stuck = bearish
        # If price near zone low and stuck = bullish
        price_position = (current_price - zone_low) / (zone_high - zone_low) if zone_high != zone_low else 0.5

        if price_position > 0.7:  # Near top of zone
            side = "SHORT"
            signal_type = "Absorption_Zone_Top"
        elif price_position < 0.3:  # Near bottom of zone
            side = "LONG"
            signal_type = "Absorption_Zone_Bottom"
        else:
            # Price in middle of zone - no clear signal
            return None

        return {
            "side": side,
            "score": 0.80 if zone_at_key_level else 0.55,
            "metadata": {
                "type": signal_type,
                "zone_low": round(zone_low, 4),
                "zone_high": round(zone_high, 4),
                "zone_levels": len(zone_levels),
                "zone_intensity": round(zone_intensity, 2),
                "zone_total_vol": round(zone_total_vol, 2),
                "fast_track": zone_at_key_level,
                "at_volume_level": zone_at_key_level,
                "poc": poc,
                "vah": vah,
                "val": val,
            },
        }

    def on_orderbook(self, ob_data: dict) -> Optional[dict]:
        self.matrix.on_orderbook(ob_data)

        now = time.time()
        bids = ob_data.get("b", [])
        asks = ob_data.get("a", [])

        if bids:
            self.last_best_bid_price = float(bids[0][0])
            self.last_best_bid_qty = float(bids[0][1])
        if asks:
            self.last_best_ask_price = float(asks[0][0])
            self.last_best_ask_qty = float(asks[0][1])

        self.dom_history.append(
            (
                now,
                {
                    "bid_price": self.last_best_bid_price,
                    "bid_qty": self.last_best_bid_qty,
                    "ask_price": self.last_best_ask_price,
                    "ask_qty": self.last_best_ask_qty,
                },
            )
        )

        return None
