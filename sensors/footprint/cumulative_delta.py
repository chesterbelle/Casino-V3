"""
Cumulative Volume Delta (CVD) Sensor with Delta Divergence Detection.

Implements Trader Dale's Delta Divergence setup:
- Price goes UP, Delta goes DOWN/FLAT → Bearish Divergence (SHORT signal)
- Price goes DOWN, Delta goes UP/FLAT → Bullish Divergence (LONG signal)

Key principle: "Price ALWAYS follows Delta eventually"

Win Rate: 70-75% (Dale's favorite setup)
"""

import time
from collections import deque
from typing import Optional

from core.market_profile import MarketProfile
from sensors.base import SensorV3
from sensors.footprint.matrix import LiveFootprintMatrix


class CumulativeDeltaSensorV3(SensorV3):
    """
    Cumulative Volume Delta (CVD) Sensor.

    Tracks the ongoing battle between aggressive buyers and sellers.
    Implements Dale's Delta Divergence: compare PRICE direction vs DELTA direction.
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        lookback_periods: int = 5,  # Number of periods to compare direction
        min_price_move_pct: float = 0.001,  # Minimum price move to consider (0.1%)
        min_delta_change_pct: float = 0.1,  # Minimum delta change as % of volume
        tick_size: float = 0.1,
        level_proximity_ticks: int = 4,
    ):
        super().__init__()
        self.window_seconds = window_seconds
        self.lookback_periods = lookback_periods
        self.min_price_move_pct = min_price_move_pct
        self.min_delta_change_pct = min_delta_change_pct
        self.tick_size = tick_size
        self.level_proximity_ticks = level_proximity_ticks

        self.matrix = LiveFootprintMatrix(window_seconds=window_seconds)
        self.market_profile = MarketProfile(tick_size=tick_size)

        # CVD Tracking
        self.current_cvd = 0.0

        # Price and Delta history for divergence calculation
        # Each entry: (timestamp, price, cvd)
        self.price_delta_history = deque(maxlen=100)

        # Periodic snapshots for direction comparison
        # Each entry: (timestamp, price, cvd)
        self.period_snapshots = deque(maxlen=20)

        # Session extremes (for context)
        self.session_high = float("-inf")
        self.session_low = float("inf")
        self.cvd_at_high = 0.0
        self.cvd_at_low = 0.0

        self._last_signal_time = 0.0
        self._signal_cooldown = 3.0  # seconds (shorter for HFT)
        self._last_snapshot_time = 0.0
        self._snapshot_interval = 5.0  # Take snapshot every 5 seconds

    @property
    def name(self) -> str:
        return "CumulativeDelta"

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        self.matrix.on_tick(tick_data)

        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("qty", 0))
        is_buyer_maker = tick_data.get("is_buyer_maker", False)

        self.market_profile.add_trade(price, vol)

        now = time.time()

        # Update CVD: If buyer is maker, seller was aggressive (hit bid)
        if is_buyer_maker:
            self.current_cvd -= vol
        else:
            self.current_cvd += vol

        # Track history
        self.price_delta_history.append((now, price, self.current_cvd))

        # Update session extremes
        if price > self.session_high:
            self.session_high = price
            self.cvd_at_high = self.current_cvd
        if price < self.session_low:
            self.session_low = price
            self.cvd_at_low = self.current_cvd

        # Take periodic snapshot for direction comparison
        if now - self._last_snapshot_time >= self._snapshot_interval:
            self.period_snapshots.append((now, price, self.current_cvd))
            self._last_snapshot_time = now

        # Check cooldown
        if now - self._last_signal_time < self._signal_cooldown:
            return None

        # Need enough snapshots
        if len(self.period_snapshots) < self.lookback_periods:
            return None

        # Calculate direction of Price and Delta
        divergence = self._detect_divergence()

        if divergence:
            poc, vah, val = self.market_profile.calculate_value_area()

            # Level Context Filter - enhance score if at key level
            prox = self.level_proximity_ticks * self.tick_size
            at_level = abs(price - poc) <= prox or abs(price - vah) <= prox or abs(price - val) <= prox

            self._last_signal_time = now

            return {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalCumulativeDelta",
                    "direction": divergence["side"],
                    "subtype": f"Delta_Divergence_{divergence['type']}",
                    "cvd": round(self.current_cvd, 2),
                    "price_direction": divergence["price_dir"],
                    "delta_direction": divergence["delta_dir"],
                    "price_change_pct": round(divergence["price_change_pct"], 4),
                    "delta_change": round(divergence["delta_change"], 2),
                    "at_volume_level": at_level,
                    "poc": poc,
                    "vah": vah,
                    "val": val,
                },
            }

        return None

    def _detect_divergence(self) -> Optional[dict]:
        """
        Detect divergence between price direction and delta direction.

        Dale's method:
        - Compare price movement over last N periods
        - Compare delta movement over same periods
        - If they diverge, signal in direction of delta
        """
        snapshots = list(self.period_snapshots)[-self.lookback_periods :]
        if len(snapshots) < 2:
            return None

        # Get start and end points
        start = snapshots[0]
        end = snapshots[-1]

        start_price = start[1]
        start_cvd = start[2]
        end_price = end[1]
        end_cvd = end[2]

        # Calculate price change
        price_change = end_price - start_price
        price_change_pct = price_change / start_price if start_price > 0 else 0

        # Calculate delta change
        delta_change = end_cvd - start_cvd

        # Skip if price move is too small (noise)
        if abs(price_change_pct) < self.min_price_move_pct:
            return None

        # Determine directions
        price_dir = "UP" if price_change > 0 else "DOWN"
        delta_dir = "UP" if delta_change > 0 else ("DOWN" if delta_change < 0 else "FLAT")

        # Detect divergences
        # Bearish: Price UP, Delta DOWN or FLAT
        if price_dir == "UP" and delta_dir in ("DOWN", "FLAT"):
            return {
                "side": "SHORT",
                "type": "Bearish",
                "price_dir": price_dir,
                "delta_dir": delta_dir,
                "price_change_pct": price_change_pct,
                "delta_change": delta_change,
            }

        # Bullish: Price DOWN, Delta UP or FLAT
        if price_dir == "DOWN" and delta_dir in ("UP", "FLAT"):
            return {
                "side": "LONG",
                "type": "Bullish",
                "price_dir": price_dir,
                "delta_dir": delta_dir,
                "price_change_pct": price_change_pct,
                "delta_change": delta_change,
            }

        return None

    def on_orderbook(self, ob_data: dict) -> Optional[dict]:
        self.matrix.on_orderbook(ob_data)
        return None
