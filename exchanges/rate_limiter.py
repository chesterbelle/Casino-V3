"""
Rate Limiter for Exchange APIs.

Prevents exceeding exchange rate limits using token bucket algorithm.

Author: Casino V3 Team
Version: 2.0.0
"""

import logging
import time
from typing import Dict

from aiolimiter import AsyncLimiter


class ExchangeRateLimiter:
    """
    Rate limiter for exchange API calls.

    Uses token bucket algorithm with separate limits per endpoint type.

    Example:
        limiter = ExchangeRateLimiter(
            orders_per_second=10,
            account_per_second=5,
            market_data_per_second=20
        )

        # Acquire token before API call
        await limiter.acquire("orders")
        result = await exchange.create_order(...)

        # Or use context manager
        async with limiter.limit("orders"):
            result = await exchange.create_order(...)
    """

    def __init__(
        self,
        orders_per_second: int = 10,
        account_per_second: int = 5,
        market_data_per_second: int = 20,
        default_per_second: int = 10,
    ):
        """
        Initialize rate limiter.

        Args:
            orders_per_second: Max order operations per second
            account_per_second: Max account operations per second
            market_data_per_second: Max market data operations per second
            default_per_second: Default rate for other operations
        """
        self.logger = logging.getLogger("RateLimiter")

        # Create limiters for different endpoint types
        self._limiters: Dict[str, AsyncLimiter] = {
            "orders": AsyncLimiter(orders_per_second, 1.0),
            "account": AsyncLimiter(account_per_second, 1.0),
            "market_data": AsyncLimiter(market_data_per_second, 1.0),
            "default": AsyncLimiter(default_per_second, 1.0),
        }

        # Track request counts
        self._request_counts: Dict[str, int] = {
            "orders": 0,
            "account": 0,
            "market_data": 0,
            "default": 0,
        }

        # Track last reset time
        self._last_reset = time.time()

    async def acquire(self, endpoint_type: str = "default", timeout: float = 60.0):
        """
        Acquire rate limit token.

        Args:
            endpoint_type: Type of endpoint ('orders', 'account', 'market_data', 'default')
            timeout: Safety timeout to prevent indefinite hangs
        """
        import asyncio

        limiter = self._limiters.get(endpoint_type, self._limiters["default"])

        # Acquire token (will wait if rate limit reached)
        try:
            await asyncio.wait_for(limiter.acquire(), timeout=timeout)
            self._request_counts[endpoint_type] = self._request_counts.get(endpoint_type, 0) + 1
            self.logger.debug(f"Rate limit acquired: {endpoint_type} ({self._request_counts[endpoint_type]} requests)")
        except asyncio.TimeoutError:
            self.logger.error(f"🚨 Rate limit acquisition TIMEOUT for {endpoint_type} after {timeout}s")
            raise TimeoutError(f"Rate limit acquisition timeout ({endpoint_type})")

    def limit(self, endpoint_type: str = "default"):
        """
        Context manager for rate limiting.

        Args:
            endpoint_type: Type of endpoint

        Example:
            async with limiter.limit("orders"):
                await exchange.create_order(...)
        """
        return RateLimitContext(self, endpoint_type)

    def get_stats(self) -> Dict[str, any]:
        """Get rate limiter statistics."""
        current_time = time.time()
        elapsed = current_time - self._last_reset

        return {
            "request_counts": dict(self._request_counts),
            "elapsed_seconds": elapsed,
            "rates": {
                endpoint: count / elapsed if elapsed > 0 else 0 for endpoint, count in self._request_counts.items()
            },
        }

    def reset_stats(self):
        """Reset statistics."""
        self._request_counts = {key: 0 for key in self._request_counts}
        self._last_reset = time.time()


class RateLimitContext:
    """Context manager for rate limiting."""

    def __init__(self, limiter: ExchangeRateLimiter, endpoint_type: str):
        self.limiter = limiter
        self.endpoint_type = endpoint_type

    async def __aenter__(self):
        await self.limiter.acquire(self.endpoint_type)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


# Binance-specific rate limits
class BinanceRateLimiter(ExchangeRateLimiter):
    """
    Rate limiter configured for Binance Futures.

    Binance limits:
    - Orders: 300 requests per minute (5/s)
    - Account: 60 requests per minute (1/s)
    - Market data: 2400 requests per minute (40/s)
    """

    def __init__(self):
        super().__init__(
            orders_per_second=5,  # Conservative (300/min = 5/s)
            account_per_second=1,  # Conservative (60/min = 1/s)
            market_data_per_second=40,  # 2400/min = 40/s
            default_per_second=5,
        )


# Hyperliquid-specific rate limits
class HyperliquidRateLimiter(ExchangeRateLimiter):
    """
    Rate limiter configured for Hyperliquid.

    Hyperliquid limits (conservative estimates):
    - Orders: 10/s
    - Account: 5/s
    - Market data: 20/s
    """

    def __init__(self):
        super().__init__(
            orders_per_second=10,
            account_per_second=5,
            market_data_per_second=20,
            default_per_second=10,
        )


def create_rate_limiter(exchange: str) -> ExchangeRateLimiter:
    """
    Create rate limiter for specific exchange.

    Args:
        exchange: Exchange name ('binance', 'hyperliquid', etc.)

    Returns:
        Configured ExchangeRateLimiter
    """
    if exchange.lower() == "binance":
        return BinanceRateLimiter()
    elif exchange.lower() == "hyperliquid":
        return HyperliquidRateLimiter()
    else:
        # Default conservative limits
        return ExchangeRateLimiter()
