"""
Caching system for Casino V3.

This module provides caching utilities to optimize performance for
repeated operations like sensor calculations and data processing.
"""

import hashlib
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    """Time-To-Live cache with automatic expiration."""

    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            else:
                del self.cache[key]  # Remove expired entry
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        expiry = time.time() + (ttl or self.default_ttl)
        self.cache[key] = (value, expiry)

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()

    def cleanup(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        current_time = time.time()
        expired_keys = [k for k, (_, exp) in self.cache.items() if current_time >= exp]

        for key in expired_keys:
            del self.cache[key]

        return len(expired_keys)

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)


class SensorCache:
    """Specialized cache for sensor calculations."""

    def __init__(self, max_size: int = 1000):
        self.cache = TTLCache(default_ttl=60)  # 1 minute TTL
        self.max_size = max_size

    def _make_key(self, sensor_name: str, candle_data: Dict[str, Any]) -> str:
        """Create cache key from sensor name and candle data."""
        # Create a hash of the relevant candle data
        key_data = f"{sensor_name}:{candle_data.get('timestamp', '')}:{candle_data.get('close', '')}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get_signal(self, sensor_name: str, candle_data: Dict[str, Any]) -> Optional[Any]:
        """Get cached signal for sensor and candle data."""
        import time

        start_time = time.time()
        key = self._make_key(sensor_name, candle_data)
        result = self.cache.get(key)

        # Record performance
        response_time = time.time() - start_time
        if result is not None:
            performance_monitor.record_hit(response_time)
        else:
            performance_monitor.record_miss(response_time)

        return result

    def set_signal(self, sensor_name: str, candle_data: Dict[str, Any], signal: Any) -> None:
        """Cache signal for sensor and candle data."""
        if self.cache.size() >= self.max_size:
            self.cache.cleanup()  # Clean up expired entries

        key = self._make_key(sensor_name, candle_data)
        self.cache.set(key, signal, ttl=60)  # 1 minute TTL


class DataCache:
    """Cache for expensive data processing operations."""

    def __init__(self):
        self.indicator_cache = TTLCache(default_ttl=300)  # 5 minutes
        self.ohlcv_cache = TTLCache(default_ttl=60)  # 1 minute

    def get_indicator(self, indicator_name: str, symbol: str, timeframe: str, period: int) -> Optional[Any]:
        """Get cached indicator value."""
        key = f"{indicator_name}:{symbol}:{timeframe}:{period}"
        return self.indicator_cache.get(key)

    def set_indicator(self, indicator_name: str, symbol: str, timeframe: str, period: int, value: Any) -> None:
        """Cache indicator value."""
        key = f"{indicator_name}:{symbol}:{timeframe}:{period}"
        self.indicator_cache.set(key, value)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Optional[Any]:
        """Get cached OHLCV data."""
        key = f"ohlcv:{symbol}:{timeframe}:{limit}"
        return self.ohlcv_cache.get(key)

    def set_ohlcv(self, symbol: str, timeframe: str, limit: int, data: Any) -> None:
        """Cache OHLCV data."""
        key = f"ohlcv:{symbol}:{timeframe}:{limit}"
        self.ohlcv_cache.set(key, data)


# Global cache instances
sensor_cache = SensorCache()
data_cache = DataCache()


# Performance monitoring
class PerformanceMonitor:
    """Monitor performance of cached operations."""

    def __init__(self):
        self.stats = {"cache_hits": 0, "cache_misses": 0, "total_operations": 0, "avg_response_time": 0.0}
        self.response_times = []

    def record_hit(self, response_time: float = 0.0):
        """Record a cache hit."""
        self.stats["cache_hits"] += 1
        self.stats["total_operations"] += 1
        if response_time > 0:
            self.response_times.append(response_time)
            self._update_avg_response_time()

    def record_miss(self, response_time: float = 0.0):
        """Record a cache miss."""
        self.stats["cache_misses"] += 1
        self.stats["total_operations"] += 1
        if response_time > 0:
            self.response_times.append(response_time)
            self._update_avg_response_time()

    def _update_avg_response_time(self):
        """Update average response time."""
        if self.response_times:
            self.stats["avg_response_time"] = sum(self.response_times[-100:]) / len(
                self.response_times[-100:]
            )  # Last 100 operations

    def get_hit_rate(self) -> float:
        """Get cache hit rate percentage."""
        total = self.stats["total_operations"]
        return (self.stats["cache_hits"] / total * 100) if total > 0 else 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return {**self.stats, "hit_rate": self.get_hit_rate(), "cache_efficiency": self._calculate_efficiency()}

    def _calculate_efficiency(self) -> str:
        """Calculate cache efficiency rating."""
        hit_rate = self.get_hit_rate()
        if hit_rate >= 80:
            return "Excellent"
        elif hit_rate >= 60:
            return "Good"
        elif hit_rate >= 40:
            return "Fair"
        else:
            return "Poor"


# Global performance monitor
performance_monitor = PerformanceMonitor()


def cached_sensor(ttl: int = 60):
    """Decorator to cache sensor calculations."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(candle_data: Dict[str, Any], *args, **kwargs) -> Any:
            sensor_name = func.__name__

            # Try to get from cache first
            cached_result = sensor_cache.get_signal(sensor_name, candle_data)
            if cached_result is not None:
                return cached_result

            # Calculate and cache
            result = func(candle_data, *args, **kwargs)
            sensor_cache.set_signal(sensor_name, candle_data, result)

            return result

        return wrapper

    return decorator


def cached_indicator(indicator_name: str, ttl: int = 300):
    """Decorator to cache indicator calculations."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(symbol: str, timeframe: str, period: int, *args, **kwargs) -> Any:
            # Try to get from cache first
            cached_result = data_cache.get_indicator(indicator_name, symbol, timeframe, period)
            if cached_result is not None:
                return cached_result

            # Calculate and cache
            result = func(symbol, timeframe, period, *args, **kwargs)
            data_cache.set_indicator(indicator_name, symbol, timeframe, period, result)

            return result

        return wrapper

    return decorator


def memory_efficient_generator(batch_size: int = 100):
    """Decorator to make functions memory efficient by processing in batches."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Check if the function returns a large dataset
            result = func(*args, **kwargs)

            # If result is a large list/generator, convert to batched generator
            if hasattr(result, "__iter__") and hasattr(result, "__len__"):
                if len(result) > batch_size:
                    # Convert to batched generator to save memory
                    def batched_generator():
                        for i in range(0, len(result), batch_size):
                            yield result[i : i + batch_size]

                    return batched_generator()

            return result

        return wrapper

    return decorator


# Utility functions
def clear_all_caches() -> None:
    """Clear all cache instances."""
    sensor_cache.cache.clear()
    data_cache.indicator_cache.clear()
    data_cache.ohlcv_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about all caches."""
    return {
        "sensor_cache": {"size": sensor_cache.cache.size(), "max_size": sensor_cache.max_size},
        "indicator_cache": {"size": data_cache.indicator_cache.size()},
        "ohlcv_cache": {"size": data_cache.ohlcv_cache.size()},
        "performance": performance_monitor.get_stats(),
    }


def optimize_memory_usage() -> Dict[str, Any]:
    """Run memory optimization routines and return stats."""
    # Clean up expired cache entries
    sensor_cleaned = sensor_cache.cache.cleanup()
    indicator_cleaned = data_cache.indicator_cache.cleanup()
    ohlcv_cleaned = data_cache.ohlcv_cache.cleanup()

    # Force garbage collection if available
    try:
        import gc

        collected = gc.collect()
    except ImportError:
        collected = 0

    return {
        "cache_cleanup": {
            "sensor_cache": sensor_cleaned,
            "indicator_cache": indicator_cleaned,
            "ohlcv_cache": ohlcv_cleaned,
        },
        "garbage_collected": collected,
        "current_stats": get_cache_stats(),
    }
