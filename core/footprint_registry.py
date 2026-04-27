"""
Footprint Registry for Absorption Scalping V1.

Maintains real-time Footprint Chart (bid/ask volume by price level) from trade stream.
Singleton pattern for shared access across components (AbsorptionDetector, SetupEngine, ExitEngine).

Phase 2.1: Initial implementation with dict-based storage.
Phase 2.1B: Migrate to numpy arrays if latency > 5ms.
"""

import logging
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FootprintData:
    """
    Footprint data for a single symbol.
    Tracks bid/ask volume by price level with sliding window (60 min).
    """

    def __init__(self, tick_size: float, window_seconds: int = 3600):
        self.tick_size = tick_size
        self.window_seconds = window_seconds

        # Price levels: {price: {ask_vol, bid_vol, delta, last_update}}
        self.levels: Dict[float, dict] = {}

        # Cumulative Volume Delta (CVD)
        self.cvd: float = 0.0
        self.cvd_history: deque = deque(maxlen=3600)  # 1 hour at 1 sample/sec

        # Metadata
        self.last_update: float = 0.0
        self.total_ask_volume: float = 0.0
        self.total_bid_volume: float = 0.0

    def round_price(self, price: float) -> float:
        """Round price to nearest tick size."""
        if self.tick_size <= 0:
            return price
        return round(price / self.tick_size) * self.tick_size

    def add_trade(self, price: float, volume: float, side: str, timestamp: float) -> float:
        """
        Add a trade to the footprint.

        Args:
            price: Trade price
            volume: Trade volume
            side: 'BUY' (aggressive buy) or 'SELL' (aggressive sell)
            timestamp: Trade timestamp (market time in backtest, wall time in live)

        Returns:
            Latency in milliseconds (for telemetry)
        """
        t_start = time.time()

        level = self.round_price(price)

        # Initialize level if new
        if level not in self.levels:
            self.levels[level] = {
                "ask_volume": 0.0,  # Aggressive buys
                "bid_volume": 0.0,  # Aggressive sells
                "delta": 0.0,
                "last_update": timestamp,
            }

        # Update volume
        if side == "BUY":
            self.levels[level]["ask_volume"] += volume
            self.total_ask_volume += volume
            delta = volume
        elif side == "SELL":
            self.levels[level]["bid_volume"] += volume
            self.total_bid_volume += volume
            delta = -volume
        else:
            logger.warning(f"⚠️ [FOOTPRINT] Unknown side: {side}")
            delta = 0.0

        # Update delta
        self.levels[level]["delta"] = self.levels[level]["ask_volume"] - self.levels[level]["bid_volume"]
        self.levels[level]["last_update"] = timestamp

        # Update CVD
        self.cvd += delta
        self.cvd_history.append((timestamp, self.cvd))

        # Update metadata
        self.last_update = timestamp

        # Calculate latency
        t_end = time.time()
        latency_ms = (t_end - t_start) * 1000

        return latency_ms

    def prune_old_levels(self, current_time: float):
        """
        Remove levels older than window_seconds.
        Called periodically to prevent memory growth.
        """
        cutoff = current_time - self.window_seconds

        levels_to_remove = []
        for level, data in self.levels.items():
            if data["last_update"] < cutoff:
                levels_to_remove.append(level)

        for level in levels_to_remove:
            data = self.levels[level]
            # Adjust CVD (remove old delta)
            self.cvd -= data["delta"]
            # Adjust totals
            self.total_ask_volume -= data["ask_volume"]
            self.total_bid_volume -= data["bid_volume"]
            # Remove level
            del self.levels[level]

        if levels_to_remove:
            logger.debug(f"🧹 [FOOTPRINT] Pruned {len(levels_to_remove)} old levels")

    def get_delta_at_level(self, price: float) -> float:
        """Get delta (ask_vol - bid_vol) at a specific price level."""
        level = self.round_price(price)
        data = self.levels.get(level)
        return data["delta"] if data else 0.0

    def get_volume_at_level(self, price: float) -> Tuple[float, float]:
        """Get (ask_volume, bid_volume) at a specific price level."""
        level = self.round_price(price)
        data = self.levels.get(level)
        if data:
            return data["ask_volume"], data["bid_volume"]
        return 0.0, 0.0

    def get_volume_profile(self, price_from: float, price_to: float) -> List[Tuple[float, float, float]]:
        """
        Get volume profile (price, ask_vol, bid_vol) in a price range.
        Returns sorted by price (ascending).

        Used for finding low/high volume nodes for dynamic TP.
        """
        profile = []
        for level, data in self.levels.items():
            if price_from <= level <= price_to:
                profile.append((level, data["ask_volume"], data["bid_volume"]))

        # Sort by price
        profile.sort(key=lambda x: x[0])
        return profile

    def get_cvd_slope(self, window_seconds: int = 5) -> float:
        """
        Calculate CVD slope (rate of change) over a time window.
        Returns delta_cvd / delta_time.

        Used to detect CVD flattening (absorption confirmation).
        """
        if len(self.cvd_history) < 2:
            return 0.0

        # Find CVD value from window_seconds ago
        cutoff = self.last_update - window_seconds
        old_cvd = None
        old_ts = None

        for ts, cvd in self.cvd_history:
            if ts >= cutoff:
                old_cvd = cvd
                old_ts = ts
                break

        if old_cvd is None or old_ts is None:
            return 0.0

        delta_cvd = self.cvd - old_cvd
        delta_time = self.last_update - old_ts

        if delta_time <= 0:
            return 0.0

        return delta_cvd / delta_time


class FootprintRegistry:
    """
    Singleton registry for Footprint data across all symbols.

    Thread-safe for concurrent access:
    - Writes (on_trade): Protected with RLock
    - Reads (get_*): Lock-free (Python GIL protects dict reads)

    Shared by:
    - AbsorptionDetector (sensor in workers) - read-only
    - AbsorptionSetupEngine (main process) - read-only
    - ExitEngine (main process) - read-only
    - OrderManager (main process) - read-only
    """

    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent re-initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.footprints: Dict[str, FootprintData] = {}
        self.tick_sizes: Dict[str, float] = {}  # symbol -> tick_size

        # Telemetry
        self.update_count: int = 0
        self.total_latency_ms: float = 0.0
        self.max_latency_ms: float = 0.0
        self.last_prune: float = 0.0
        self.prune_interval: float = 60.0  # Prune every 60 seconds

        logger.info("🏗️ FootprintRegistry initialized (Singleton)")

    def register_symbol(self, symbol: str, tick_size: float):
        """
        Register a symbol with its tick size.
        Must be called before on_trade() for that symbol.
        """
        with self._lock:
            if symbol not in self.footprints:
                self.footprints[symbol] = FootprintData(tick_size=tick_size)
                self.tick_sizes[symbol] = tick_size
                logger.info(f"📊 [FOOTPRINT] Registered {symbol} (tick_size={tick_size})")

    def on_trade(self, symbol: str, price: float, volume: float, side: str, timestamp: float):
        """
        Update footprint with a new trade.

        Args:
            symbol: Trading symbol
            price: Trade price
            volume: Trade volume
            side: 'BUY' or 'SELL'
            timestamp: Trade timestamp (market time or wall time)

        Telemetry: T0a_footprint_update_ts
        """
        # Auto-register symbol if not registered (with default tick size)
        if symbol not in self.footprints:
            logger.warning(f"⚠️ [FOOTPRINT] Symbol {symbol} not registered, using default tick_size=0.5")
            self.register_symbol(symbol, tick_size=0.5)

        with self._lock:
            footprint = self.footprints[symbol]
            latency_ms = footprint.add_trade(price, volume, side, timestamp)

            # Update telemetry
            self.update_count += 1
            self.total_latency_ms += latency_ms
            self.max_latency_ms = max(self.max_latency_ms, latency_ms)

            # Log slow updates
            if latency_ms > 5.0:
                logger.warning(
                    f"⚠️ [LATENCY] FootprintRegistry slow: {latency_ms:.2f}ms "
                    f"(symbol={symbol}, levels={len(footprint.levels)})"
                )

            # Periodic pruning
            if timestamp - self.last_prune > self.prune_interval:
                self._prune_all(timestamp)
                self.last_prune = timestamp

            # Periodic telemetry logging (every 1000 updates)
            if self.update_count % 1000 == 0:
                avg_latency = self.total_latency_ms / self.update_count
                logger.info(
                    f"📊 [FOOTPRINT] Updates: {self.update_count} | "
                    f"Avg Latency: {avg_latency:.2f}ms | "
                    f"Max Latency: {self.max_latency_ms:.2f}ms"
                )

    def _prune_all(self, current_time: float):
        """Prune old levels from all symbols."""
        for symbol, footprint in self.footprints.items():
            footprint.prune_old_levels(current_time)

    def get_footprint(self, symbol: str) -> Optional[FootprintData]:
        """
        Get footprint data for a symbol (read-only).
        Returns None if symbol not registered.
        """
        return self.footprints.get(symbol)

    def get_delta_at_level(self, symbol: str, price: float) -> float:
        """Get delta at a specific price level."""
        footprint = self.footprints.get(symbol)
        return footprint.get_delta_at_level(price) if footprint else 0.0

    def get_cvd(self, symbol: str) -> float:
        """Get current CVD for a symbol."""
        footprint = self.footprints.get(symbol)
        return footprint.cvd if footprint else 0.0

    def get_cvd_slope(self, symbol: str, window_seconds: int = 5) -> float:
        """Get CVD slope (rate of change) over a time window."""
        footprint = self.footprints.get(symbol)
        return footprint.get_cvd_slope(window_seconds) if footprint else 0.0

    def get_volume_profile(self, symbol: str, price_from: float, price_to: float) -> List[Tuple[float, float, float]]:
        """Get volume profile in a price range."""
        footprint = self.footprints.get(symbol)
        return footprint.get_volume_profile(price_from, price_to) if footprint else []

    def get_telemetry(self) -> dict:
        """Get telemetry data for monitoring."""
        avg_latency = self.total_latency_ms / self.update_count if self.update_count > 0 else 0.0

        return {
            "update_count": self.update_count,
            "avg_latency_ms": avg_latency,
            "max_latency_ms": self.max_latency_ms,
            "symbols_tracked": len(self.footprints),
            "total_levels": sum(len(fp.levels) for fp in self.footprints.values()),
        }

    def reset(self):
        """Reset all footprint data (for testing or session reset)."""
        with self._lock:
            for footprint in self.footprints.values():
                footprint.levels.clear()
                footprint.cvd = 0.0
                footprint.cvd_history.clear()
                footprint.total_ask_volume = 0.0
                footprint.total_bid_volume = 0.0

            logger.info("🧹 [FOOTPRINT] All footprints reset")


# Singleton instance (lazy initialization)
footprint_registry = FootprintRegistry()
