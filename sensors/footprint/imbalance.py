import time
from typing import Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3
from sensors.footprint.matrix import LiveFootprintMatrix


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

    def __init__(
        self,
        imbalance_ratio: float = 3.0,
        min_volume: float = 1.0,
        window_seconds: float = 30.0,
        tick_size: float = 0.1,
        level_proximity_ticks: int = 4,
    ):
        super().__init__()
        self.imbalance_ratio = imbalance_ratio
        self.min_volume = min_volume
        self.level_proximity_ticks = level_proximity_ticks
        self.matrix = LiveFootprintMatrix(window_seconds=window_seconds)
        self.market_profile = MarketProfile(tick_size=tick_size)

        # Cooldown to avoid blasting the engine with signals for the same imbalance
        self._last_signal_time = 0.0
        self._signal_cooldown = 2.0  # 2 seconds cooldown

    @property
    def name(self) -> str:
        return "FootprintImbalance"

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        """React to every new tick."""
        # 1. Update the memory matrix and global profile
        self.matrix.on_tick(tick_data)

        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("qty", 0))
        self.market_profile.add_trade(price, vol)

        # 2. Check for signal cooldown
        now = time.time()
        if now - self._last_signal_time < self._signal_cooldown:
            return None

        # 3. Analyze current matrix profile for Imbalances
        profile = self.matrix.profile
        if not profile:
            return None

        imbalances = []
        unfinished_business = []
        poc, vah, val = self.market_profile.calculate_value_area()

        # Phase 660: Trader Dale Level Filter
        prox = self.level_proximity_ticks * self.market_profile.tick_size
        at_level = abs(price - poc) <= prox or abs(price - vah) <= prox or abs(price - val) <= prox

        # Phase 650.2: Check for Unfinished Business (Failed Auctions) at extremes
        prices = list(profile.keys())
        if prices:
            high = max(prices)
            low = min(prices)

            top_vol = profile.get(high, {})
            bottom_vol = profile.get(low, {})

            # Unfinished Business at High (0 bid volume at the absolute top)
            if top_vol.get("bid", 0.0) == 0 and top_vol.get("ask", 0.0) > 0:
                unfinished_business.append({"side": "LONG_TARGET", "price": high, "type": "Unfinished_High"})

            # Unfinished Business at Low (0 ask volume at the absolute bottom)
            if bottom_vol.get("ask", 0.0) == 0 and bottom_vol.get("bid", 0.0) > 0:
                unfinished_business.append({"side": "SHORT_TARGET", "price": low, "type": "Unfinished_Low"})

        # Analyze each price level in the sliding window
        for p, v in profile.items():
            bid_vol = v.get("bid", 0.0)
            ask_vol = v.get("ask", 0.0)

            # Skip low volume levels to avoid noise
            if (bid_vol + ask_vol) < self.min_volume:
                continue

            density = self.market_profile.get_cluster_density(p)

            # Check for Buy Imbalance (Aggressive Buying hit the ask)
            if ask_vol > (bid_vol * self.imbalance_ratio) and bid_vol > 0:
                imbalances.append({"side": "LONG", "price": p, "ratio": ask_vol / bid_vol, "density": density})
            elif ask_vol > self.min_volume and bid_vol == 0:
                imbalances.append({"side": "LONG", "price": p, "ratio": 99.9, "density": density})

            # Check for Sell Imbalance (Aggressive Selling hit the bid)
            elif bid_vol > (ask_vol * self.imbalance_ratio) and ask_vol > 0:
                imbalances.append({"side": "SHORT", "price": p, "ratio": bid_vol / ask_vol, "density": density})
            elif bid_vol > self.min_volume and ask_vol == 0:
                imbalances.append({"side": "SHORT", "price": p, "ratio": 99.9, "density": density})

        if not imbalances:
            return None

        long_imbalances = [i for i in imbalances if i["side"] == "LONG"]
        short_imbalances = [i for i in imbalances if i["side"] == "SHORT"]

        # 4. Determine Direction (Simplest: Majority rules for micro-trend)
        signal = None
        if len(long_imbalances) > len(short_imbalances):
            avg_density = sum(i["density"] for i in long_imbalances) / len(long_imbalances)
            signal = {
                "side": "LONG",
                "score": 1.0 if at_level else 0.4,
                "metadata": {
                    "imbalances": len(long_imbalances),
                    "type": "Live Buy Imbalance",
                    "fast_track": at_level,
                    "at_volume_level": at_level,
                    "cluster_density": round(avg_density, 2),
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "unfinished_business_targets": unfinished_business,
                },
            }
        elif len(short_imbalances) > len(long_imbalances):
            avg_density = sum(i["density"] for i in short_imbalances) / len(short_imbalances)
            signal = {
                "side": "SHORT",
                "score": 1.0 if at_level else 0.4,
                "metadata": {
                    "imbalances": len(short_imbalances),
                    "type": "Live Sell Imbalance",
                    "fast_track": at_level,
                    "at_volume_level": at_level,
                    "cluster_density": round(avg_density, 2),
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "unfinished_business_targets": unfinished_business,
                },
            }

        # If no strict imbalance, but there IS unfinished business, we can still emit a context-only signal
        if not signal and unfinished_business:
            signal = {
                "side": "NEUTRAL",
                "score": 0.5,
                "metadata": {
                    "type": "Unfinished_Business_Context",
                    "fast_track": False,
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "unfinished_business_targets": unfinished_business,
                },
            }

        if signal:
            self._last_signal_time = now
            return signal

        return None

    def on_orderbook(self, ob_data: dict) -> Optional[dict]:
        """React to orderbook updates."""
        self.matrix.on_orderbook(ob_data)
        return None
