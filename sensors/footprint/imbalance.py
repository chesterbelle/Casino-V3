import time
from typing import Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3
from sensors.footprint.matrix import LiveFootprintMatrix
from sensors.quant.volatility_regime import RollingZScore


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
        imbalance_ratio: float = 4.0,  # Fix #3: Increased from 3.0 to 4.0 for higher quality signals
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

        # Phase 2: Volatility Regime Z-Scores
        self.buy_ratio_zscore = RollingZScore(window_size=200)
        self.sell_ratio_zscore = RollingZScore(window_size=200)
        self.min_zscore_anomaly = 4.0  # Fix #3: Increased from 3.0 to 4.0 StdDev for anomaly

        # Cooldown to avoid blasting the engine with signals for the same imbalance
        self._last_signal_time = 0.0
        self._signal_cooldown = 0.5  # 500ms metric cooldown for HFT

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

        # Phase 650: Dynamic Volume Thresholds
        # Scale min_volume relative to current profile's average cluster density
        avg_density = self.market_profile.get_avg_cluster_density()
        dynamic_min = max(self.min_volume, avg_density * 0.75)

        # Analyze each price level in the sliding window
        for p, v in profile.items():
            bid_vol = v.get("bid", 0.0)
            ask_vol = v.get("ask", 0.0)
            total_vol = bid_vol + ask_vol

            # Skip low volume levels relative to current market liquidity
            if total_vol < dynamic_min:
                continue

            density = self.market_profile.get_cluster_density(p)

            # Phase 2: Dynamic Z-Scores
            if bid_vol > 0:
                buy_ratio = ask_vol / bid_vol
                self.buy_ratio_zscore.update(buy_ratio)

                if self.buy_ratio_zscore.is_ready:
                    z = self.buy_ratio_zscore.get_zscore(buy_ratio)
                    if z >= self.min_zscore_anomaly and ask_vol > bid_vol:
                        imbalances.append(
                            {"side": "LONG", "price": p, "ratio": buy_ratio, "density": density, "zscore": z}
                        )
                # Fallback to static if not ready
                elif buy_ratio > self.imbalance_ratio:
                    imbalances.append(
                        {"side": "LONG", "price": p, "ratio": buy_ratio, "density": density, "zscore": 0.0}
                    )

            elif ask_vol > dynamic_min and bid_vol == 0:
                imbalances.append({"side": "LONG", "price": p, "ratio": 99.9, "density": density, "zscore": 9.9})

            if ask_vol > 0:
                sell_ratio = bid_vol / ask_vol
                self.sell_ratio_zscore.update(sell_ratio)

                if self.sell_ratio_zscore.is_ready:
                    z = self.sell_ratio_zscore.get_zscore(sell_ratio)
                    if z >= self.min_zscore_anomaly and bid_vol > ask_vol:
                        imbalances.append(
                            {"side": "SHORT", "price": p, "ratio": sell_ratio, "density": density, "zscore": z}
                        )
                elif sell_ratio > self.imbalance_ratio:
                    imbalances.append(
                        {"side": "SHORT", "price": p, "ratio": sell_ratio, "density": density, "zscore": 0.0}
                    )

            elif bid_vol > dynamic_min and ask_vol == 0:
                imbalances.append({"side": "SHORT", "price": p, "ratio": 99.9, "density": density, "zscore": 9.9})

        if not imbalances:
            return None

        long_imbalances = [i for i in imbalances if i["side"] == "LONG"]
        short_imbalances = [i for i in imbalances if i["side"] == "SHORT"]

        # 4. Determine Direction (Tactical Event Generation)
        signal = None
        if len(long_imbalances) > len(short_imbalances):
            avg_density = sum(i["density"] for i in long_imbalances) / len(long_imbalances)
            max_zscore = max((i["zscore"] for i in long_imbalances), default=0.0)
            signal = {
                "side": "TACTICAL",  # No longer guessing LONG/SHORT
                "metadata": {
                    "tactical_type": "TacticalImbalance",
                    "direction": "LONG",
                    "imbalances": len(long_imbalances),
                    "at_volume_level": at_level,
                    "cluster_density": round(avg_density, 2),
                    "max_zscore": round(max_zscore, 2),
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "price": price,
                    "unfinished_business_targets": unfinished_business,
                },
            }
        elif len(short_imbalances) > len(long_imbalances):
            avg_density = sum(i["density"] for i in short_imbalances) / len(short_imbalances)
            max_zscore = max((i["zscore"] for i in short_imbalances), default=0.0)
            signal = {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalImbalance",
                    "direction": "SHORT",
                    "imbalances": len(short_imbalances),
                    "at_volume_level": at_level,
                    "cluster_density": round(avg_density, 2),
                    "max_zscore": round(max_zscore, 2),
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                    "price": price,
                    "unfinished_business_targets": unfinished_business,
                },
            }

        # If no strict imbalance, but there IS unfinished business, emit context
        if not signal and unfinished_business:
            signal = {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalContext",
                    "context_reason": "Unfinished_Business",
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
