"""
Custom exceptions for Casino V3 trading system.

This module defines all custom exceptions used throughout the application
for consistent error handling and better debugging.
"""

from typing import Any, Dict, Optional


class CasinoError(Exception):
    """Base exception for all Casino V3 errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ValidationError(CasinoError):
    """Raised when input validation fails."""

    pass


class ConfigurationError(CasinoError):
    """Raised when configuration is invalid or missing."""

    pass


class TradingError(CasinoError):
    """Raised when trading operations fail."""

    pass


class ExchangeError(TradingError):
    """Raised when exchange operations fail."""

    pass


class BalanceError(TradingError):
    """Raised when balance operations fail."""

    pass


class PositionError(TradingError):
    """Raised when position operations fail."""

    pass


class SensorError(CasinoError):
    """Raised when sensor operations fail."""

    pass


class GeminiError(CasinoError):
    """Raised when Gemini operations fail."""

    pass


class TableError(CasinoError):
    """Raised when table operations fail."""

    pass


class DataError(CasinoError):
    """Raised when data operations fail."""

    pass


class PerformanceError(CasinoError):
    """Raised when performance limits are exceeded."""

    pass


# Convenience functions for error creation
def create_validation_error(field: str, value: Any, reason: str) -> ValidationError:
    """Create a validation error with standardized format."""
    return ValidationError(f"Validation failed for {field}", {"field": field, "value": value, "reason": reason})


def create_balance_error(operation: str, required: float, available: float) -> BalanceError:
    """Create a balance error with standardized format."""
    return BalanceError(
        f"Insufficient balance for {operation}", {"operation": operation, "required": required, "available": available}
    )


def create_position_error(action: str, symbol: str, reason: str) -> PositionError:
    """Create a position error with standardized format."""
    return PositionError(
        f"Position operation failed: {action} on {symbol}", {"action": action, "symbol": symbol, "reason": reason}
    )
