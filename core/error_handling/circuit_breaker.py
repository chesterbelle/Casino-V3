"""
Circuit Breaker Pattern Implementation.

Prevents cascading failures by stopping requests to failing services.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is failing, requests are rejected immediately
- HALF_OPEN: Testing if service has recovered

Author: Casino V3 Team
Version: 2.0.0
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Optional


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    Example:
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            half_open_max_calls=3
        )

        async with breaker:
            result = await risky_operation()
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
        name: str = "default",
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Max calls to allow in half-open state
            name: Name for logging/metrics
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

        self.logger = logging.getLogger(f"CircuitBreaker.{name}")

    @property
    def state(self) -> CircuitState:
        """Get current state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN

    async def call(self, func: Callable, *args, **kwargs):
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args, **kwargs: Arguments for function

        Returns:
            Result of function

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Original exception from function
        """
        async with self._lock:
            # Check if we should attempt recovery
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN. " f"Retry after {self._time_until_retry():.1f}s"
                    )

            # Limit calls in half-open state
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is HALF_OPEN. " f"Max test calls reached."
                    )
                self._half_open_calls += 1

        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception:
            await self.record_failure()
            raise

    async def record_success(self):
        """Handle successful call."""
        async with self._lock:
            self._failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._transition_to_closed()

    async def record_failure(self):
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Immediate open on failure in half-open
                self._transition_to_open()
            elif self._failure_count >= self.failure_threshold:
                self._transition_to_open()

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.recovery_timeout

    def _time_until_retry(self) -> float:
        """Calculate time until retry is allowed."""
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.recovery_timeout - elapsed)

    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        self.logger.info(f"🟢 Circuit breaker '{self.name}' → CLOSED (recovered)")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0

    def _transition_to_open(self):
        """Transition to OPEN state."""
        self.logger.warning(
            f"🔴 Circuit breaker '{self.name}' → OPEN " f"(failures: {self._failure_count}/{self.failure_threshold})"
        )
        self._state = CircuitState.OPEN
        self._success_count = 0
        self._half_open_calls = 0

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self.logger.info(f"🟡 Circuit breaker '{self.name}' → HALF_OPEN (testing recovery)")
        self._state = CircuitState.HALF_OPEN
        self._success_count = 0
        self._half_open_calls = 0

    async def check_availability(self):
        """Check if execution is allowed, raising error if not."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN. " f"Retry after {self._time_until_retry():.1f}s"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is HALF_OPEN. " f"Max test calls reached."
                    )
                self._half_open_calls += 1

    async def __aenter__(self):
        """Context manager entry."""
        await self.check_availability()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            # Success
            await self.record_success()
        else:
            # Failure
            await self.record_failure()
        return False  # Don't suppress exception

    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        self.logger.info(f"🔄 Circuit breaker '{self.name}' manually reset")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "time_until_retry": self._time_until_retry() if self._state == CircuitState.OPEN else 0.0,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass
