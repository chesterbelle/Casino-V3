"""
Big Orders Sensor - Detects large individual trades (Icebergs/Smart Money).

Implements Trader Dale's Big Order setup:
- Filter trades to show only large orders (3-5x average size)
- When big order appears at key level → Confirmation signal
- Big buyer at support = LONG signal
- Big seller at resistance = SHORT signal

Win Rate: 65-70% (confirmation setup)
"""

import time
from collections import deque
from typing import Optional

from sensors.base import SensorV3


class BigOrderSensor(SensorV3):
    """
    Detects large individual trades that indicate smart money activity.

    Uses a sliding window to calculate average trade size and flags
    trades that are significantly larger than average.
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        size_multiplier: float = 3.0,  # Trade must be 3x average to be "big"
        min_trades_for_avg: int = 50,  # Minimum trades before calculating average
        level_proximity_ticks: int = 4,
        tick_size: float = 0.1,
        signal_cooldown: float = 5.0,
    ):
        super().__init__()
        self.window_seconds = window_seconds
        self.size_multiplier = size_multiplier
        self.min_trades_for_avg = min_trades_for_avg
        self.level_proximity_ticks = level_proximity_ticks
        self.tick_size = tick_size
        self.signal_cooldown = signal_cooldown

        # Trade history: (timestamp, price, volume, side)
        self.trade_history = deque(maxlen=500)

        # Key levels from external context
        self._key_levels = {}  # Set by calculate() from SessionValueArea

        # Stats
        self._avg_trade_size = 0.0
        self._total_trades = 0
        self._big_orders_detected = 0

        self._last_signal_time = 0.0

    @property
    def name(self) -> str:
        return "BigOrderSensor"

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        """
        Process incoming trade tick.

        Returns signal if a big order is detected at a key level.
        """
        now = time.time()

        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("qty", 0))
        is_buyer_maker = tick_data.get("is_buyer_maker", False)

        # Determine aggressive side
        # is_buyer_maker=True means seller was aggressive (hit the bid)
        side = "SELL" if is_buyer_maker else "BUY"

        # Add to history
        self.trade_history.append((now, price, vol, side))
        self._total_trades += 1

        # Prune old trades
        cutoff = now - self.window_seconds
        while self.trade_history and self.trade_history[0][0] < cutoff:
            self.trade_history.popleft()

        # Calculate average trade size
        if len(self.trade_history) < self.min_trades_for_avg:
            return None

        total_vol = sum(t[2] for t in self.trade_history)
        self._avg_trade_size = total_vol / len(self.trade_history)

        # Check if this is a big order
        if vol < self._avg_trade_size * self.size_multiplier:
            return None

        self._big_orders_detected += 1

        # Check cooldown
        if now - self._last_signal_time < self.signal_cooldown:
            return None

        # Check if at key level
        level_info = self._check_key_level(price)

        if level_info["at_level"]:
            # Generate signal based on big order side and level
            signal = self._generate_signal(side, price, vol, level_info)
            if signal:
                self._last_signal_time = now
                return signal

        return None

    def _check_key_level(self, price: float) -> dict:
        """
        Check if price is at a key level.

        Uses key levels from SessionValueArea context.
        """
        if not self._key_levels:
            return {"at_level": False, "level_type": None, "level_price": None}

        prox = self.level_proximity_ticks * self.tick_size

        # Check each key level
        for level_type, level_price in self._key_levels.items():
            if level_price is None or level_price <= 0:
                continue
            if abs(price - level_price) <= prox:
                return {
                    "at_level": True,
                    "level_type": level_type,
                    "level_price": level_price,
                }

        return {"at_level": False, "level_type": None, "level_price": None}

    def _generate_signal(self, side: str, price: float, vol: float, level_info: dict) -> Optional[dict]:
        """
        Generate trading signal based on big order at key level.

        Logic:
        - Big BUY at support (VAL, IB_LOW, POC below price) → LONG
        - Big SELL at resistance (VAH, IB_HIGH, POC above price) → SHORT
        """
        level_type = level_info["level_type"]
        level_price = level_info["level_price"]

        # Determine if level is support or resistance
        is_support = level_type in ("VAL", "IB_LOW", "POC") and price >= level_price * 0.9999
        is_resistance = level_type in ("VAH", "IB_HIGH", "POC") and price <= level_price * 1.0001

        signal = None

        # Big buyer at support = LONG
        if side == "BUY" and is_support:
            signal = {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalBigOrder",
                    "direction": "LONG",
                    "subtype": "Big_Buyer_at_Support",
                    "big_order_side": side,
                    "big_order_vol": round(vol, 4),
                    "avg_trade_vol": round(self._avg_trade_size, 4),
                    "size_ratio": round(vol / self._avg_trade_size, 2),
                    "level_type": level_type,
                    "level_price": level_price,
                },
            }

        # Big seller at resistance = SHORT
        elif side == "SELL" and is_resistance:
            signal = {
                "side": "TACTICAL",
                "metadata": {
                    "tactical_type": "TacticalBigOrder",
                    "direction": "SHORT",
                    "subtype": "Big_Seller_at_Resistance",
                    "big_order_side": side,
                    "big_order_vol": round(vol, 4),
                    "avg_trade_vol": round(self._avg_trade_size, 4),
                    "size_ratio": round(vol / self._avg_trade_size, 2),
                    "level_type": level_type,
                    "level_price": level_price,
                },
            }

        return signal

    def calculate(self, context: dict) -> Optional[dict]:
        """
        Update key levels from SessionValueArea context.

        This is called by the sensor manager with candle context.
        """
        # Extract key levels from SessionValueArea if available
        # The context may contain a 'session_context' key with VA levels
        session_context = context.get("session_context", {})

        if session_context:
            self._key_levels = {
                "POC": session_context.get("poc"),
                "VAH": session_context.get("vah"),
                "VAL": session_context.get("val"),
                "IB_HIGH": session_context.get("ib_high"),
                "IB_LOW": session_context.get("ib_low"),
            }

        # This sensor primarily works via on_tick, not calculate
        return None

    def get_stats(self) -> dict:
        """Return sensor statistics."""
        return {
            "total_trades": self._total_trades,
            "avg_trade_size": round(self._avg_trade_size, 4),
            "big_orders_detected": self._big_orders_detected,
            "big_order_threshold": round(self._avg_trade_size * self.size_multiplier, 4),
        }
