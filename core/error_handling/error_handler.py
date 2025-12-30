"""
Centralized Error Handler for Casino V3.

Provides intelligent error handling with:
- Error classification (retriable vs fatal)
- Exponential backoff with jitter
- Circuit breaker integration
- Retry logic
- Error metrics

Author: Casino V3 Team
Version: 2.0.0
"""

import asyncio
import logging
import os
import random
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from exchanges.resilience.error_classifier import ErrorCategory, ErrorClassifier

from .circuit_breaker import CircuitBreaker

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    backoff_base: float = 1.0  # Base delay in seconds
    backoff_max: float = 60.0  # Max delay in seconds
    backoff_factor: float = 2.0  # Exponential factor
    jitter: bool = True  # Add randomness to backoff


class ErrorHandler:
    """
    Centralized error handler with intelligent retry logic.

    Example:
        handler = ErrorHandler()

        # With automatic retry
        result = await handler.execute(
            risky_function,
            arg1, arg2,
            retry_config=RetryConfig(max_retries=5)
        )

        # With circuit breaker
        result = await handler.execute_with_breaker(
            "api_calls",
            risky_function,
            arg1, arg2
        )
    """

    def __init__(self):
        self.logger = logging.getLogger("ErrorHandler")
        self.classifier = ErrorClassifier()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._error_counts: dict[str, int] = {}
        self.shutdown_mode: bool = False

    def get_circuit_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker.

        Args:
            name: Unique name for the circuit breaker
            failure_threshold: Failures before opening
            recovery_timeout: Seconds before attempting recovery
            half_open_max_calls: Max calls in half-open state

        Returns:
            CircuitBreaker instance
        """
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
                name=name,
            )
        return self._circuit_breakers[name]

    def set_shutdown_mode(self, enabled: bool):
        """
        Enable/disable shutdown mode.
        When enabled, circuit breaker blocks are bypassed for critical cleanup.
        """
        self.shutdown_mode = enabled
        self.logger.info(f"🛑 ErrorHandler shutdown mode: {'ENABLED' if enabled else 'DISABLED'}")

    async def execute(
        self,
        func: Callable[..., T],
        *args,
        retry_config: Optional[RetryConfig] = None,
        context: str = "unknown",
        **kwargs,
    ) -> T:
        """
        Execute function with automatic retry on retriable errors.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            retry_config: Retry configuration (uses defaults if None)
            context: Context for logging/metrics
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            Exception: If all retries exhausted or error is not retriable
        """
        config = retry_config or RetryConfig()
        last_exception = None

        for attempt in range(config.max_retries):
            try:
                result = await func(*args, **kwargs)

                # Reset error count on success
                if context in self._error_counts:
                    del self._error_counts[context]

                return result

            except (asyncio.CancelledError, Exception) as e:
                last_exception = e

                # Track error
                self._error_counts[context] = self._error_counts.get(context, 0) + 1

                # If it's a CancelledError, we re-raise immediately but it might have been
                # triggered by a timeout in execute_with_breaker which recorded a failure.
                if isinstance(e, asyncio.CancelledError):
                    raise e

                # Classify error
                classification = self.classifier.classify(e)

                # Log error
                self.logger.warning(
                    f"⚠️ Error in {context} (attempt {attempt + 1}/{config.max_retries}): "
                    f"{classification.category.value} | {str(e)[:100]}"
                )

                # Check if retriable
                if not classification.is_retriable:
                    self.logger.error(
                        f"❌ Non-retriable error in {context}: "
                        f"{classification.category.value} | {classification.message}"
                    )
                    raise

                # Check if max retries reached
                if attempt >= config.max_retries - 1:
                    self.logger.error(f"❌ Max retries ({config.max_retries}) exhausted for {context}")
                    raise

                # Calculate backoff delay
                delay = self._calculate_backoff(
                    attempt=attempt,
                    base=config.backoff_base,
                    factor=config.backoff_factor,
                    max_delay=config.backoff_max,
                    jitter=config.jitter,
                )

                # Use classifier's suggested delay if available
                if classification.retry_delay:
                    delay = min(delay, classification.retry_delay)

                self.logger.info(
                    f"🔄 Retrying {context} in {delay:.2f}s " f"(attempt {attempt + 2}/{config.max_retries})"
                )
                await asyncio.sleep(delay)

        # Should never reach here, but just in case
        raise last_exception

    async def execute_with_breaker(
        self,
        breaker_name: str,
        func: Callable[..., T],
        *args,
        retry_config: Optional[RetryConfig] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> T:
        """
        Execute function with circuit breaker protection and retry logic.

        CRITICAL: Only records failures for systemic errors (Network, Timeout).
        Validation errors (INVALID_ORDER) do NOT trip the breaker.

        Args:
            breaker_name: Name for the circuit breaker
            func: Async function to execute
            *args: Positional arguments for func
            retry_config: Retry configuration
            timeout: Optional upper bound timeout for entire operation (seconds).
                     If provided, the entire operation (including retries) must
                     complete within this time or TimeoutError is raised.
            **kwargs: Keyword arguments for func
        """
        breaker = self.get_circuit_breaker(breaker_name)

        # Wrap function execution with MANUAL breaker management to filter errors
        async def wrapped():
            # 1. Check if allowed (Bypass if in shutdown mode)
            if self.shutdown_mode:
                self.logger.debug(f"🛑 Shutdown Mode Active: Bypassing breaker check for {breaker_name}")
            else:
                await breaker.check_availability()

            try:
                # 2. Execute
                result = await func(*args, **kwargs)

                # 3. Success
                await breaker.record_success()
                return result

            except (asyncio.CancelledError, Exception) as e:
                # 4. Handle Failure - Selective Recording
                classification = self.classifier.classify(e)

                # These categories are data/logic errors, NOT system failures
                # They should NOT trip the circuit breaker
                ignored_categories = [
                    ErrorCategory.INVALID_ORDER,
                    ErrorCategory.INVALID_SYMBOL,
                    ErrorCategory.INSUFFICIENT_FUNDS,
                    ErrorCategory.AUTHENTICATION,
                    ErrorCategory.AUTHORIZATION,
                ]

                if classification.category in ignored_categories:
                    # PROOF OF LIFE: If the exchange responds with a validation error,
                    # it means the service is healthy and the circuit should close.
                    await breaker.record_success()
                else:
                    # Record failure for actual system issues (Network, Timeout, etc)
                    # or if the call was cancelled (which we treat as a timeout/failure).
                    await breaker.record_failure()

                raise e

        # Execute with retry logic
        context = f"{breaker_name}.{func.__name__}"

        try:
            if timeout:
                # Apply upper bound timeout to entire operation (including retries)
                return await asyncio.wait_for(
                    self.execute(wrapped, retry_config=retry_config, context=context),
                    timeout=timeout,
                )
            else:
                return await self.execute(wrapped, retry_config=retry_config, context=context)
        except asyncio.TimeoutError:
            # Record failure on timeout (system is unresponsive)
            await breaker.record_failure()
            self.logger.error(f"❌ Operation timeout ({timeout}s) for {context}")
            raise

    def _calculate_backoff(
        self,
        attempt: int,
        base: float,
        factor: float,
        max_delay: float,
        jitter: bool,
    ) -> float:
        """
        Calculate exponential backoff delay with optional jitter.

        Args:
            attempt: Current attempt number (0-indexed)
            base: Base delay in seconds
            factor: Exponential factor
            max_delay: Maximum delay
            jitter: Whether to add jitter

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base * (factor ^ attempt)
        delay = base * (factor**attempt)

        # Cap at max_delay
        delay = min(delay, max_delay)

        # Add jitter (±25% randomness)
        if jitter:
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0.1, delay)  # Ensure positive

        return delay

    def get_error_stats(self) -> dict[str, Any]:
        """
        Get error statistics.

        Returns:
            Dictionary with error counts and circuit breaker states
        """
        return {
            "error_counts": dict(self._error_counts),
            "circuit_breakers": {name: breaker.get_stats() for name, breaker in self._circuit_breakers.items()},
            "classifier_metrics": self.classifier.get_metrics(),
        }

    def reset_circuit_breaker(self, name: str):
        """Manually reset a circuit breaker."""
        if name in self._circuit_breakers:
            self._circuit_breakers[name].reset()
            self.logger.info(f"🔄 Circuit breaker '{name}' manually reset")
        else:
            self.logger.warning(f"⚠️ Circuit breaker '{name}' not found")

    def reset_all_circuit_breakers(self):
        """Reset all circuit breakers."""
        for breaker in self._circuit_breakers.values():
            breaker.reset()
        self.logger.info("🔄 All circuit breakers reset")


# Global error handler instance
_global_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get global error handler instance."""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler


def restart_program():
    """
    Restarts the current program.
    Note: This function does not return. Any cleanup handlers should be called before this.
    """
    logger = logging.getLogger("ErrorHandler")
    logger.critical("🚨 CRITICAL ERROR: Forcing process restart...")

    try:
        # Flush stdout/stderr
        sys.stdout.flush()
        sys.stderr.flush()

        # Restart
        python = sys.executable
        os.execv(python, [python] + sys.argv)
    except Exception as e:
        logger.critical(f"❌ Failed to restart process: {e}")
        sys.exit(1)
