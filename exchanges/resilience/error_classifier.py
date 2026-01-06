"""
Error Classifier - Casino V3

Sistema de clasificación de errores para determinar si son retriables.
Inspirado en Hummingbot's error handling.

Características:
- Clasifica errores en retriables vs no-retriables
- Detecta errores específicos de exchanges
- Sugiere acciones correctivas
- Métricas de errores

Author: Casino V3 Team
Version: 2.0.0
"""

import logging
import re
from enum import Enum
from typing import Any, Dict, Optional


class ErrorCategory(Enum):
    """Categorías de errores."""

    # Errores retriables (temporales)
    NETWORK = "network"  # Errores de red
    TIMEOUT = "timeout"  # Timeouts
    RATE_LIMIT = "rate_limit"  # Rate limit excedido
    SERVER_ERROR = "server_error"  # Error del servidor (5xx)
    TEMPORARY = "temporary"  # Otros errores temporales

    # Errores NO retriables (permanentes)
    AUTHENTICATION = "authentication"  # Credenciales inválidas
    AUTHORIZATION = "authorization"  # Sin permisos
    INVALID_SYMBOL = "invalid_symbol"  # Símbolo no existe
    INVALID_ORDER = "invalid_order"  # Orden inválida
    INSUFFICIENT_FUNDS = "insufficient_funds"  # Balance insuficiente
    MARKET_CLOSED = "market_closed"  # Mercado cerrado
    GRACEFUL_SHUTDOWN = "graceful_shutdown"  # Expected error during shutdown
    PERMANENT = "permanent"  # Otros errores permanentes

    # Errores desconocidos
    UNKNOWN = "unknown"


class ErrorAction(Enum):
    """Acciones sugeridas para cada error."""

    RETRY = "retry"  # Reintentar con backoff
    RETRY_IMMEDIATE = "retry_immediate"  # Reintentar inmediatamente
    FAIL = "fail"  # Fallar inmediatamente
    WAIT_AND_RETRY = "wait_and_retry"  # Esperar más tiempo y reintentar
    FIX_AND_RETRY = "fix_and_retry"  # Corregir parámetros y reintentar


class ErrorClassification:
    """Resultado de clasificación de un error."""

    def __init__(
        self,
        category: ErrorCategory,
        is_retriable: bool,
        suggested_action: ErrorAction,
        message: str,
        retry_delay: Optional[float] = None,
    ):
        """
        Initialize error classification.

        Args:
            category: Categoría del error
            is_retriable: Si el error es retriable
            suggested_action: Acción sugerida
            message: Mensaje descriptivo
            retry_delay: Delay sugerido para retry (segundos)
        """
        self.category = category
        self.is_retriable = is_retriable
        self.suggested_action = suggested_action
        self.message = message
        self.retry_delay = retry_delay

    def __repr__(self) -> str:
        return (
            f"ErrorClassification("
            f"category={self.category.value}, "
            f"retriable={self.is_retriable}, "
            f"action={self.suggested_action.value})"
        )


class ErrorClassifier:
    """
    Clasificador de errores para exchanges.

    Analiza excepciones y determina si son retriables y qué acción tomar.

    Ejemplo:
        classifier = ErrorClassifier()

        try:
            await connector.fetch_balance()
        except Exception as e:
            classification = classifier.classify(e)

            if classification.is_retriable:
                await asyncio.sleep(classification.retry_delay)
                # Retry
            else:
                # Fail
                raise
    """

    # Patrones de errores retriables
    RETRIABLE_PATTERNS = [
        # Network errors
        (r"connection.*reset", ErrorCategory.NETWORK),
        (r"connection.*refused", ErrorCategory.NETWORK),
        (r"connection.*timeout", ErrorCategory.TIMEOUT),
        (r"timed out", ErrorCategory.TIMEOUT),
        (r"timeout", ErrorCategory.TIMEOUT),
        (r"network.*error", ErrorCategory.NETWORK),
        (r"socket.*error", ErrorCategory.NETWORK),
        # Server errors
        (r"5\d{2}", ErrorCategory.SERVER_ERROR),  # 5xx errors
        (r"internal.*server.*error", ErrorCategory.SERVER_ERROR),
        (r"service.*unavailable", ErrorCategory.SERVER_ERROR),
        (r"bad.*gateway", ErrorCategory.SERVER_ERROR),
        (r"gateway.*timeout", ErrorCategory.SERVER_ERROR),
        # Rate limiting
        (r"rate.*limit", ErrorCategory.RATE_LIMIT),
        (r"too.*many.*requests", ErrorCategory.RATE_LIMIT),
        (r"429", ErrorCategory.RATE_LIMIT),
        # Binance Futures - Rate Limiting
        (r"-1015", ErrorCategory.RATE_LIMIT),  # Too many new orders
        (r"-1003", ErrorCategory.RATE_LIMIT),  # Too many requests queued
        # Binance Futures - Temporary/Retriable
        (r"-1001", ErrorCategory.TEMPORARY),  # Disconnected from server
        (r"-1000", ErrorCategory.TEMPORARY),  # Unknown error (often temporary)
        (r"-1021", ErrorCategory.TEMPORARY),  # Timestamp outside recvWindow (Fix: Auto-Resync)
        (r"-2022", ErrorCategory.TEMPORARY),  # Binance: ReduceOnly Order rejected (Sync Lag)
        (r"-4118", ErrorCategory.TEMPORARY),  # Binance: ReduceOnly Order failed (Sync Lag)
        # NOTE: -4164 moved to NON_RETRIABLE - it's a validation error, not a sync issue
        # Temporary
        (r"temporary.*error", ErrorCategory.TEMPORARY),
        (r"try.*again", ErrorCategory.TEMPORARY),
    ]

    # Patrones de errores NO retriables
    NON_RETRIABLE_PATTERNS = [
        # Authentication
        (r"invalid.*api.*key", ErrorCategory.AUTHENTICATION),
        (r"invalid.*signature", ErrorCategory.AUTHENTICATION),
        (r"authentication.*failed", ErrorCategory.AUTHENTICATION),
        (r"unauthorized", ErrorCategory.AUTHENTICATION),
        (r"401", ErrorCategory.AUTHENTICATION),
        (r"-2015", ErrorCategory.AUTHENTICATION),  # Binance: Invalid API-key format
        (r"-1022", ErrorCategory.AUTHENTICATION),  # Binance: Signature invalid
        # Authorization
        (r"forbidden", ErrorCategory.AUTHORIZATION),
        (r"permission.*denied", ErrorCategory.AUTHORIZATION),
        (r"403", ErrorCategory.AUTHORIZATION),
        # Invalid parameters
        (r"invalid.*symbol", ErrorCategory.INVALID_SYMBOL),
        (r"symbol.*not.*found", ErrorCategory.INVALID_SYMBOL),
        (r"invalid.*order", ErrorCategory.INVALID_ORDER),
        (r"order.*invalid", ErrorCategory.INVALID_ORDER),
        # Binance Futures - Invalid Order
        (r"-2021", ErrorCategory.INVALID_ORDER),  # Order would immediately trigger
        (r"-4131", ErrorCategory.INVALID_ORDER),  # Percent price is out of range
        (r"-1111", ErrorCategory.INVALID_ORDER),  # Precision is over max limit
        (r"-1116", ErrorCategory.INVALID_ORDER),  # Invalid orderType
        (r"-1117", ErrorCategory.INVALID_ORDER),  # Invalid side
        (r"-2011", ErrorCategory.INVALID_ORDER),  # Binance: Unknown order sent (cancel failed)
        (r"-2013", ErrorCategory.INVALID_ORDER),  # Binance: Order does not exist
        (r"-4003", ErrorCategory.INVALID_ORDER),  # Quantity less than minQty
        (r"-4164", ErrorCategory.INVALID_ORDER),  # Binance: Notional too small (validation, not retry)
        # Insufficient funds
        (r"insufficient.*funds", ErrorCategory.INSUFFICIENT_FUNDS),
        (r"insufficient.*balance", ErrorCategory.INSUFFICIENT_FUNDS),
        (r"not.*enough.*balance", ErrorCategory.INSUFFICIENT_FUNDS),
        (r"-2019", ErrorCategory.INSUFFICIENT_FUNDS),  # Binance: Margin is insufficient
        (r"-4028", ErrorCategory.INSUFFICIENT_FUNDS),  # Binance: Insufficient available balance
        # Market closed
        (r"market.*closed", ErrorCategory.MARKET_CLOSED),
        (r"trading.*disabled", ErrorCategory.MARKET_CLOSED),
        # Graceful shutdown (expected when we intentionally close connections)
        (r"connection.*to.*remote.*host.*was.*lost", ErrorCategory.GRACEFUL_SHUTDOWN),
        (r"lost.*websocket.*connection", ErrorCategory.GRACEFUL_SHUTDOWN),
        (r"websocket.*closed", ErrorCategory.GRACEFUL_SHUTDOWN),
    ]

    def __init__(self):
        """Initialize error classifier."""
        self.logger = logging.getLogger("ErrorClassifier")

        # Métricas
        self._total_classified = 0
        self._retriable_count = 0
        self._non_retriable_count = 0
        self._category_counts: Dict[ErrorCategory, int] = {}

        self.logger.info("✅ ErrorClassifier initialized")

    def classify(self, error: Exception) -> ErrorClassification:
        """
        Clasifica un error.

        Args:
            error: Excepción a clasificar

        Returns:
            ErrorClassification con categoría y acción sugerida
        """
        self._total_classified += 1

        # Convertir error a string para análisis
        error_str = str(error).lower()
        error_type = type(error).__name__

        # 1. Intentar clasificar por tipo de excepción
        classification = self._classify_by_type(error, error_type)
        if classification:
            self._update_metrics(classification)
            return classification

        # 2. Intentar clasificar por mensaje (retriables primero)
        for pattern, category in self.RETRIABLE_PATTERNS:
            if re.search(pattern, error_str, re.IGNORECASE):
                classification = self._create_retriable_classification(category, error_str)
                self._update_metrics(classification)
                return classification

        # 3. Intentar clasificar por mensaje (no retriables)
        for pattern, category in self.NON_RETRIABLE_PATTERNS:
            if re.search(pattern, error_str, re.IGNORECASE):
                classification = self._create_non_retriable_classification(category, error_str)
                self._update_metrics(classification)
                return classification

        # 4. Error desconocido - ser conservador (no retriable)
        if error_type in ["CancelledError", "TimeoutError"]:
            return ErrorClassification(
                category=ErrorCategory.GRACEFUL_SHUTDOWN if error_type == "CancelledError" else ErrorCategory.TIMEOUT,
                is_retriable=False,
                suggested_action=ErrorAction.FAIL,
                message=f"System error: {error_type}",
            )

        self.logger.warning(f"⚠️ Unknown error type: {error_type} | Message: {error_str[:100]}")
        classification = ErrorClassification(
            category=ErrorCategory.UNKNOWN,
            is_retriable=False,  # Conservador: no retry por defecto
            suggested_action=ErrorAction.FAIL,
            message=f"Unknown error: {error_str[:100]}",
        )
        self._update_metrics(classification)
        return classification

    def _classify_by_type(self, error: Exception, error_type: str) -> Optional[ErrorClassification]:
        """Clasifica error por tipo de excepción."""
        # CRITICAL: Circuit breaker errors ARE retriable - just need to wait
        if "circuitbreaker" in error_type.lower() or "circuit_breaker" in error_type.lower():
            # Extract retry delay from error message if available
            import re

            error_str = str(error)
            retry_match = re.search(r"retry after (\d+\.?\d*)s?", error_str, re.IGNORECASE)
            retry_delay = float(retry_match.group(1)) if retry_match else 60.0

            return ErrorClassification(
                category=ErrorCategory.TEMPORARY,
                is_retriable=True,
                suggested_action=ErrorAction.WAIT_AND_RETRY,
                message=f"Circuit breaker open, waiting {retry_delay}s before retry",
                retry_delay=retry_delay,
            )

        # Network errors (retriables)
        if any(
            name in error_type.lower()
            for name in ["timeout", "connection", "connector", "network", "socket", "oserror", "ioerror", "aiohttp"]
        ):
            return self._create_retriable_classification(ErrorCategory.NETWORK, str(error))

        # Authentication errors (no retriables)
        if "authentication" in error_type.lower() or "auth" in error_type.lower():
            return self._create_non_retriable_classification(ErrorCategory.AUTHENTICATION, str(error))

        # Permission errors (no retriables)
        if "permission" in error_type.lower() or "forbidden" in error_type.lower():
            return self._create_non_retriable_classification(ErrorCategory.AUTHORIZATION, str(error))

        return None

    def _create_retriable_classification(self, category: ErrorCategory, message: str) -> ErrorClassification:
        """Crea clasificación para error retriable."""
        # Determinar delay según categoría
        if category == ErrorCategory.RATE_LIMIT:
            retry_delay = 60.0  # 1 minuto para rate limit
            action = ErrorAction.WAIT_AND_RETRY
        elif category == ErrorCategory.TIMEOUT:
            retry_delay = 5.0  # 5 segundos para timeout
            action = ErrorAction.RETRY
        elif category == ErrorCategory.SERVER_ERROR:
            retry_delay = 10.0  # 10 segundos para server error
            action = ErrorAction.RETRY
        else:
            retry_delay = 2.0  # 2 segundos por defecto
            action = ErrorAction.RETRY

        return ErrorClassification(
            category=category,
            is_retriable=True,
            suggested_action=action,
            message=f"{category.value}: {message[:100]}",
            retry_delay=retry_delay,
        )

    def _create_non_retriable_classification(self, category: ErrorCategory, message: str) -> ErrorClassification:
        """Crea clasificación para error NO retriable."""
        # Determinar acción según categoría
        if category == ErrorCategory.INVALID_ORDER:
            action = ErrorAction.FIX_AND_RETRY
        elif category == ErrorCategory.GRACEFUL_SHUTDOWN:
            # Expected during shutdown - don't log as error, allow process to exit
            self.logger.info(f"🔌 Shutdown-related: {message[:60]}")
            action = ErrorAction.FAIL  # Don't retry, just exit cleanly
        else:
            action = ErrorAction.FAIL

        return ErrorClassification(
            category=category,
            is_retriable=False,
            suggested_action=action,
            message=f"{category.value}: {message[:100]}",
        )

    def _update_metrics(self, classification: ErrorClassification) -> None:
        """Actualiza métricas de clasificación."""
        if classification.is_retriable:
            self._retriable_count += 1
        else:
            self._non_retriable_count += 1

        # Contar por categoría
        category = classification.category
        self._category_counts[category] = self._category_counts.get(category, 0) + 1

    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas del clasificador."""
        return {
            "total_classified": self._total_classified,
            "retriable_count": self._retriable_count,
            "non_retriable_count": self._non_retriable_count,
            "retriable_rate": self._retriable_count / self._total_classified if self._total_classified > 0 else 0,
            "category_counts": {cat.value: count for cat, count in self._category_counts.items()},
        }

    def reset_metrics(self) -> None:
        """Resetea métricas."""
        self._total_classified = 0
        self._retriable_count = 0
        self._non_retriable_count = 0
        self._category_counts.clear()
        self.logger.info("🔄 Metrics reset")
