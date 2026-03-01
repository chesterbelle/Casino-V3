import time
from typing import Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3
from sensors.footprint.matrix import LiveFootprintMatrix


class FootprintAbsorptionV3(SensorV3):
    """
    Footprint Absorption Sensor.

    Detects absorption: High volume traded at a price level but price fails to continue.

    Logic:
    - High Ask Volume at the High of the candle -> Absorption (Sellers absorbing Buyers) -> SHORT signal.
    - High Bid Volume at the Low of the candle -> Absorption (Buyers absorbing Sellers) -> LONG signal.
    """

    def __init__(
        self,
        min_volume_ratio: float = 2.0,
        pullback_ticks: int = 5,
        window_seconds: float = 30.0,
        tick_size: float = 0.1,
    ):
        super().__init__()
        self.min_volume_ratio = min_volume_ratio
        self.pullback_ticks = pullback_ticks
        self.matrix = LiveFootprintMatrix(window_seconds=window_seconds)
        self.market_profile = MarketProfile(tick_size=tick_size)

        # DOM Limit Order Caching
        self.last_best_bid_qty = 0.0
        self.last_best_ask_qty = 0.0
        self.last_best_bid_price = 0.0
        self.last_best_ask_price = 0.0
        self.dom_history = []  # Time-series of DOM state

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
        # Simple heuristic: Use the average distance between levels
        prices.sort()
        avg_tick_size = (
            sum(prices[i + 1] - prices[i] for i in range(len(prices) - 1)) / len(prices) if len(prices) > 1 else 0.5
        )

        pullback_distance = avg_tick_size * self.pullback_ticks

        poc, vah, val = self.market_profile.calculate_value_area()

        signal = None

        # --- Scenario 1: Absorption at High (Bearish) ---
        # 1. High Volume at the top
        # 2. Price has pulled back from the High
        # 3. [Phase 650.3]: There was a massive Limit Sell Order at that high acting as a wall
        top_vol = profile.get(high, {"bid": 0.0, "ask": 0.0})
        if top_vol["ask"] > avg_vol_per_level * self.min_volume_ratio:
            if current_price <= high - pullback_distance:
                intensity = top_vol["ask"] / (avg_vol_per_level if avg_vol_per_level > 0 else 1.0)

                # Check DOM History for a wall at `high`
                wall_confirmed = False
                wall_size = 0.0
                for ts, dom in self.dom_history:
                    if abs(dom["ask_price"] - high) < self.market_profile.tick_size:
                        if dom["ask_qty"] > (avg_vol_per_level * 5):  # Arbitrary "Massive" wall threshold
                            wall_confirmed = True
                            wall_size = dom["ask_qty"]
                            break

                signal = {
                    "side": "SHORT",
                    "score": 0.9 if wall_confirmed else 0.6,  # Higher score if DOM confirms
                    "metadata": {
                        "type": "Live_Absorption_High",
                        "vol": top_vol["ask"],
                        "fast_track": wall_confirmed,  # Only fast-track if confirmed by DOM
                        "absorption_intensity": round(intensity, 2),
                        "dom_wall_confirmed": wall_confirmed,
                        "dom_wall_size": wall_size,
                        "poc": poc,
                        "vah": vah,
                        "val": val,
                    },
                }

        # --- Scenario 2: Absorption at Low (Bullish) ---
        # 1. High Volume at the bottom
        # 2. Price has bounced up from the Low
        # 3. [Phase 650.3]: Massive Limit Buy Order wall at that low
        low_vol = profile.get(low, {"bid": 0.0, "ask": 0.0})
        if not signal and low_vol["bid"] > avg_vol_per_level * self.min_volume_ratio:
            if current_price >= low + pullback_distance:
                intensity = low_vol["bid"] / (avg_vol_per_level if avg_vol_per_level > 0 else 1.0)

                wall_confirmed = False
                wall_size = 0.0
                for ts, dom in self.dom_history:
                    if abs(dom["bid_price"] - low) < self.market_profile.tick_size:
                        if dom["bid_qty"] > (avg_vol_per_level * 5):
                            wall_confirmed = True
                            wall_size = dom["bid_qty"]
                            break

                signal = {
                    "side": "LONG",
                    "score": 0.9 if wall_confirmed else 0.6,
                    "metadata": {
                        "type": "Live_Absorption_Low",
                        "vol": low_vol["bid"],
                        "fast_track": wall_confirmed,
                        "absorption_intensity": round(intensity, 2),
                        "dom_wall_confirmed": wall_confirmed,
                        "dom_wall_size": wall_size,
                        "poc": poc,
                        "vah": vah,
                        "val": val,
                    },
                }

        if signal:
            self._last_signal_time = now
            return signal

        return None

    def on_orderbook(self, ob_data: dict) -> Optional[dict]:
        self.matrix.on_orderbook(ob_data)

        # Phase 650.3 Cache DOM for verification
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

        # Cleanup old DOM
        if len(self.dom_history) > 100:
            self.dom_history = self.dom_history[-50:]

        return None
