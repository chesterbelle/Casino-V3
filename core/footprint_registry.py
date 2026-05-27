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
        self.total_bid_volume: float = 0.0
        self.total_ask_volume: float = 0.0

        # Performance Cache: {metric_key: (timestamp, value)}
        self._cache: Dict[str, Tuple[float, any]] = {}

        # Update counter for timing sampling
        self._update_count: int = 0

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
        # Sample timing every 100 trades to reduce syscall overhead
        t_start = time.time() if self._update_count % 100 == 0 else 0.0

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
        elif side == "UNKNOWN":
            # Just a price update, no volume for footprint
            return 0.0
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
        self._update_count += 1

        # Calculate latency (sampled)
        if t_start > 0.0:
            t_end = time.time()
            latency_ms = (t_end - t_start) * 1000
        else:
            latency_ms = 0.0

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
        # Check cache first: key = f"slope_{window_seconds}"
        cache_key = f"slope_{window_seconds}"
        if cache_key in self._cache:
            cache_ts, cache_val = self._cache[cache_key]
            if cache_ts == self.last_update:
                return cache_val

        if len(self.cvd_history) < 2:
            return 0.0

        # Find CVD value from window_seconds ago using binary search
        cutoff = self.last_update - window_seconds
        old_cvd = None
        old_ts = None

        # Binary search for the first entry >= cutoff
        lo, hi = 0, len(self.cvd_history) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            ts, cvd = self.cvd_history[mid]
            if ts < cutoff:
                lo = mid + 1
            else:
                old_cvd = cvd
                old_ts = ts
                hi = mid - 1

        if old_cvd is None or old_ts is None:
            return 0.0

        delta_cvd = self.cvd - old_cvd
        delta_time = self.last_update - old_ts

        slope = 0.0
        if delta_time > 0:
            slope = delta_cvd / delta_time

        # Update cache
        self._cache[cache_key] = (self.last_update, slope)
        return slope

    def get_exhaustion_metrics(self, window_long: float = 10.0, window_short: float = 2.0) -> dict:
        """Phase A (AMT): Compute delta declining and volume declining metrics.

        Measures whether the aggressive flow is EXHAUSTING (declining) or still active.
        Uses CVD history to compute:
        - delta_ratio: |delta_short| / |delta_long| — lower = more exhaustion
        - volume_ratio: volume_short / volume_long — lower = volume dropping

        Args:
            window_long: Longer lookback window in seconds (default 10s)
            window_short: Shorter lookback window in seconds (default 2s)

        Returns:
            dict with delta_ratio, volume_ratio, delta_long, delta_short, vol_long, vol_short
        """
        # Check cache first: key = f"exh_{window_long}_{window_short}"
        cache_key = f"exh_{window_long}_{window_short}"
        if cache_key in self._cache:
            cache_ts, cache_val = self._cache[cache_key]
            if cache_ts == self.last_update:
                return cache_val

        now = self.last_update
        if len(self.cvd_history) < 4:
            res = {
                "delta_ratio": 1.0,
                "volume_ratio": 1.0,
                "delta_long": 0,
                "delta_short": 0,
                "vol_long": 0,
                "vol_short": 0,
                "ready": False,
            }
            self._cache[cache_key] = (now, res)
            return res

        cutoff_long = now - window_long
        cutoff_short = now - window_short

        # Binary search for window boundaries
        cvd_at_long_start = None
        cvd_at_short_start = None
        cvd_now = self.cvd_history[-1][1]
        n_long = 0
        n_short = 0
        idx_long = len(self.cvd_history)  # default: no entries in window
        idx_short = len(self.cvd_history)

        # Find long window start using binary search
        lo, hi = 0, len(self.cvd_history) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            ts, cvd = self.cvd_history[mid]
            if ts < cutoff_long:
                lo = mid + 1
            else:
                cvd_at_long_start = cvd
                idx_long = mid
                hi = mid - 1

        # Find short window start using binary search
        lo, hi = 0, len(self.cvd_history) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            ts, cvd = self.cvd_history[mid]
            if ts < cutoff_short:
                lo = mid + 1
            else:
                cvd_at_short_start = cvd
                idx_short = mid
                hi = mid - 1

        # Count entries in each window
        n_long = len(self.cvd_history) - idx_long
        n_short = len(self.cvd_history) - idx_short

        if cvd_at_long_start is None:
            cvd_at_long_start = self.cvd_history[0][1]
        if cvd_at_short_start is None:
            cvd_at_short_start = cvd_at_long_start

        delta_long = cvd_now - cvd_at_long_start
        delta_short = cvd_now - cvd_at_short_start

        # Delta ratio: is the aggressor exhausting?
        delta_ratio = abs(delta_short) / abs(delta_long) if abs(delta_long) > 1e-9 else 1.0

        # Volume proxy: number of trades (CVD entries) in each window
        vol_ratio = n_short / (n_long * (window_short / window_long)) if n_long > 0 else 1.0

        res = {
            "delta_ratio": round(delta_ratio, 3),
            "volume_ratio": round(vol_ratio, 3),
            "delta_long": round(delta_long, 2),
            "delta_short": round(delta_short, 2),
            "vol_long": n_long,
            "vol_short": n_short,
            "ready": True,
        }

        # Update cache
        self._cache[cache_key] = (now, res)
        return res


class FootprintRegistry:
    """
    Singleton registry for Footprint data across all symbols.

    Thread-safe for concurrent access:
    - Writes (on_trade): Protected with RLock
    - Reads (get_*): Lock-free (Python GIL protects dict reads)

    Shared by:
    - AbsorptionDetector (sensor in workers) - read-only
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

            # Periodic telemetry logging (every 1000 updates)
            if self.update_count % 1000 == 0:
                avg_latency = self.total_latency_ms / self.update_count
                logger.info(
                    f"📊 [FOOTPRINT] Updates: {self.update_count} | "
                    f"Avg Latency: {avg_latency:.2f}ms | "
                    f"Max Latency: {self.max_latency_ms:.2f}ms"
                )

        # Periodic pruning — OUTSIDE the lock to avoid blocking on_trade()
        if timestamp - self.last_prune > self.prune_interval:
            self.last_prune = timestamp
            self._prune_all_deferred(current_time=timestamp)

    def _prune_all(self, current_time: float):
        """Prune old levels from all symbols."""
        for symbol, footprint in self.footprints.items():
            footprint.prune_old_levels(current_time)

    def _prune_all_deferred(self, current_time: float):
        """Prune old levels outside the main lock to avoid blocking on_trade()."""
        # Take a snapshot of footprints (safe to iterate without lock for pruning)
        snapshots = list(self.footprints.items())
        for symbol, footprint in snapshots:
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

    def get_exhaustion(self, symbol: str, window_long: float = 10.0, window_short: float = 2.0) -> dict:
        """Get exhaustion metrics for a symbol. See FootprintData.get_exhaustion_metrics()."""
        footprint = self.footprints.get(symbol)
        if not footprint:
            return {"delta_ratio": 1.0, "volume_ratio": 1.0, "ready": False}
        return footprint.get_exhaustion_metrics(window_long, window_short)

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
