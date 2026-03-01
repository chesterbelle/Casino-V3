"""
Live Footprint Matrix
Mantains a sliding-window orderflow profile for HFT Scalping.
"""

import time
from collections import deque
from typing import Dict, List, Tuple


class LiveFootprintMatrix:
    """
    Mantains a real-time orderflow matrix by tracking the last N ticks
    and the latest orderbook snapshot.
    """

    def __init__(self, window_seconds: float = 30.0, max_ticks: int = 5000):
        self.window_seconds = window_seconds
        self.max_ticks = max_ticks

        # State
        self.ticks = deque()  # Store (timestamp_ms, price, volume, side)
        self.profile: Dict[float, Dict[str, float]] = {}  # price -> {'bid': vol, 'ask': vol}

        # Orderbook State
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.bids: List[Tuple[float, float]] = []
        self.asks: List[Tuple[float, float]] = []

        # Metrics
        self.delta = 0.0
        self.total_volume = 0.0

    def on_tick(self, tick_data: dict):
        """Process a new trade tick."""
        ts = tick_data.get("timestamp", time.time() * 1000)
        price = float(tick_data.get("price", 0))
        vol = float(tick_data.get("volume", 0))
        side = tick_data.get("side", "UNKNOWN")  # 'BUY'/'SELL' or 'BID'/'ASK'

        # Normalize side to footprint terminology
        # A 'BUY' trade hits the ASK, so it's Ask Volume (Agresive Buy).
        # A 'SELL' trade hits the BID, so it's Bid Volume (Agresive Sell).
        if side.upper() in ("BUY", "ASK"):
            f_side = "ask"
            self.delta += vol
        elif side.upper() in ("SELL", "BID"):
            f_side = "bid"
            self.delta -= vol
        else:
            return  # Ignore unknown sides

        # Add to deque
        self.ticks.append((ts, price, vol, f_side))
        self.total_volume += vol

        # Add to profile
        if price not in self.profile:
            self.profile[price] = {"bid": 0.0, "ask": 0.0}
        self.profile[price][f_side] += vol

        # Prune old ticks
        self._prune(ts)

    def on_orderbook(self, ob_data: dict):
        """Update the latest orderbook state."""
        self.bids = ob_data.get("bids", [])
        self.asks = ob_data.get("asks", [])

        if self.bids:
            self.best_bid = float(self.bids[0][0])
        if self.asks:
            self.best_ask = float(self.asks[0][0])

    def _prune(self, current_ts: float):
        """Remove ticks older than the window or beyond max_ticks."""
        cutoff_ts = current_ts - (self.window_seconds * 1000)

        while self.ticks and (len(self.ticks) > self.max_ticks or self.ticks[0][0] < cutoff_ts):
            old_ts, old_price, old_vol, old_side = self.ticks.popleft()

            # Remove from profile
            if old_price in self.profile:
                self.profile[old_price][old_side] -= old_vol
                # Clean up empty levels to avoid memory leaks
                if self.profile[old_price]["bid"] <= 1e-8 and self.profile[old_price]["ask"] <= 1e-8:
                    del self.profile[old_price]

            # Update metrics
            self.total_volume -= old_vol
            if old_side == "ask":
                self.delta -= old_vol
            else:
                self.delta += old_vol

    def get_poc(self) -> float:
        """Get the Point of Control (price level with max volume)."""
        if not self.profile:
            return 0.0

        poc_price = 0.0
        max_vol = -1.0

        for price, vols in self.profile.items():
            lvl_vol = vols["bid"] + vols["ask"]
            if lvl_vol > max_vol:
                max_vol = lvl_vol
                poc_price = price

        return poc_price
