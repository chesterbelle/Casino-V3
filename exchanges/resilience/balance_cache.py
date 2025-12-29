"""
Balance Cache - Casino V3

Sistema de cache y fallback para balance inspirado en Hummingbot.
Evita crashes cuando el exchange falla temporalmente.

Características:
- Cache con TTL (Time To Live)
- Fallback a último valor conocido
- Staleness detection
- Múltiples fuentes de balance
- Métricas de confiabilidad

Author: Casino V3 Team
Version: 2.0.0
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class BalanceSource(Enum):
    """Fuente del balance."""

    EXCHANGE_FRESH = "exchange_fresh"  # Fetch directo del exchange (< TTL)
    EXCHANGE_CACHED = "exchange_cached"  # Cache del exchange (> TTL pero < max_age)
    CALCULATED = "calculated"  # Calculado localmente después de trades
    FALLBACK = "fallback"  # Último valor conocido (stale)
    UNKNOWN = "unknown"  # No disponible


@dataclass
class BalanceSnapshot:
    """
    Snapshot de balance con metadata.

    Inspirado en Hummingbot's balance tracking.
    """

    balance: float
    currency: str
    source: BalanceSource
    timestamp: float
    is_stale: bool = False
    staleness_seconds: float = 0.0

    # Metadata adicional
    free: Optional[float] = None
    used: Optional[float] = None
    total: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializa a dict."""
        return {
            "balance": self.balance,
            "currency": self.currency,
            "source": self.source.value,
            "timestamp": self.timestamp,
            "is_stale": self.is_stale,
            "staleness_seconds": self.staleness_seconds,
            "free": self.free,
            "used": self.used,
            "total": self.total,
        }


class BalanceCache:
    """
    Cache de balance con fallback inteligente.

    Inspirado en Hummingbot's balance management.

    Estrategia de fallback:
    1. Intento 1: Fetch fresco del exchange
    2. Intento 2: Cache reciente (< cache_ttl)
    3. Intento 3: Balance calculado localmente
    4. Intento 4: Último valor conocido (< max_age)
    5. Fallo: Lanzar error crítico

    Ejemplo:
        cache = BalanceCache(cache_ttl=30, max_age=300)

        # Actualizar con fetch del exchange
        cache.update_from_exchange(balance_data)

        # Obtener balance con fallback
        snapshot = cache.get_balance_safe()
        if snapshot.is_stale:
            logger.warning(f"Balance stale: {snapshot.staleness_seconds}s")
    """

    def __init__(
        self,
        cache_ttl: float = 30.0,  # Cache válido por 30 segundos
        max_age: float = 300.0,  # Máximo 5 minutos de staleness
        currency: str = "USD",
    ):
        """
        Initialize BalanceCache.

        Args:
            cache_ttl: Tiempo en segundos que el cache es considerado "fresco"
            max_age: Tiempo máximo en segundos antes de considerar el balance inválido
            currency: Moneda base (USD, USDT, etc.)
        """
        self.logger = logging.getLogger("BalanceCache")

        # Configuración
        self._cache_ttl = cache_ttl
        self._max_age = max_age
        self._currency = currency

        # Cache principal (del exchange)
        self._cached_balance: Optional[float] = None
        self._cache_timestamp: float = 0.0

        # Balance calculado (después de trades)
        self._calculated_balance: Optional[float] = None
        self._calculated_timestamp: float = 0.0

        # Último valor conocido (fallback final)
        self._last_known_balance: Optional[float] = None
        self._last_known_timestamp: float = 0.0

        # Métricas
        self._total_fetches = 0
        self._cache_hits = 0
        self._fallback_hits = 0
        self._failed_fetches = 0

        self.logger.info(f"✅ BalanceCache initialized | TTL: {cache_ttl}s | Max age: {max_age}s")

    def update_from_exchange(self, balance_data: Dict[str, Any]) -> BalanceSnapshot:
        """
        Actualiza cache con datos del exchange.

        Args:
            balance_data: Respuesta del exchange (formato CCXT)

        Returns:
            BalanceSnapshot actualizado

        Raises:
            ValueError: Si balance_data es inválido
        """
        # Validar y extraer balance
        balance = self._extract_balance(balance_data)

        # Actualizar cache
        self._cached_balance = balance
        self._cache_timestamp = time.time()

        # Actualizar último conocido
        self._last_known_balance = balance
        self._last_known_timestamp = time.time()

        self._total_fetches += 1

        self.logger.debug(f"💰 Balance updated from exchange: {balance:.2f} {self._currency}")

        return BalanceSnapshot(
            balance=balance,
            currency=self._currency,
            source=BalanceSource.EXCHANGE_FRESH,
            timestamp=self._cache_timestamp,
            is_stale=False,
            staleness_seconds=0.0,
            free=balance_data.get("free", {}).get(self._currency),
            used=balance_data.get("used", {}).get(self._currency),
            total=balance_data.get("total", {}).get(self._currency),
        )

    def update_calculated(self, balance: float) -> None:
        """
        Actualiza balance calculado localmente.

        Esto se usa después de ejecutar trades para tener un balance
        estimado sin necesidad de fetch del exchange.

        Args:
            balance: Balance calculado
        """
        self._calculated_balance = balance
        self._calculated_timestamp = time.time()

        self.logger.debug(f"🧮 Balance calculated: {balance:.2f} {self._currency}")

    def get_balance_safe(self) -> BalanceSnapshot:
        """
        Obtiene balance con fallback inteligente.

        Estrategia:
        1. Balance calculado (si existe y es MÁS RECIENTE que cache)
        2. Cache fresco (< cache_ttl)
        3. Cache stale (< max_age)
        4. Último conocido (< max_age)
        5. Error crítico

        Returns:
            BalanceSnapshot con balance y metadata

        Raises:
            RuntimeError: Si no hay balance disponible
        """
        current_time = time.time()

        # 1. Balance calculado (si es más reciente que el cache)
        if self._calculated_balance is not None:
            calc_age = current_time - self._calculated_timestamp

            # Usar calculado si es más reciente que el cache
            if self._calculated_timestamp > self._cache_timestamp and calc_age < self._cache_ttl:
                self.logger.info(f"🧮 Using calculated balance: {calc_age:.1f}s old")
                return BalanceSnapshot(
                    balance=self._calculated_balance,
                    currency=self._currency,
                    source=BalanceSource.CALCULATED,
                    timestamp=self._calculated_timestamp,
                    is_stale=False,
                    staleness_seconds=calc_age,
                )

        # 2. Cache fresco del exchange
        if self._cached_balance is not None:
            age = current_time - self._cache_timestamp

            if age < self._cache_ttl:
                # Cache fresco
                self._cache_hits += 1
                return BalanceSnapshot(
                    balance=self._cached_balance,
                    currency=self._currency,
                    source=BalanceSource.EXCHANGE_FRESH,
                    timestamp=self._cache_timestamp,
                    is_stale=False,
                    staleness_seconds=age,
                )

            elif age < self._max_age:
                # Cache stale pero aceptable
                self._cache_hits += 1
                self.logger.warning(f"⚠️ Using stale cache: {age:.1f}s old")
                return BalanceSnapshot(
                    balance=self._cached_balance,
                    currency=self._currency,
                    source=BalanceSource.EXCHANGE_CACHED,
                    timestamp=self._cache_timestamp,
                    is_stale=True,
                    staleness_seconds=age,
                )

        # 3. Último conocido (fallback final)
        if self._last_known_balance is not None:
            age = current_time - self._last_known_timestamp

            if age < self._max_age:
                self._fallback_hits += 1
                self.logger.warning(f"⚠️ Using fallback balance: {age:.1f}s old")
                return BalanceSnapshot(
                    balance=self._last_known_balance,
                    currency=self._currency,
                    source=BalanceSource.FALLBACK,
                    timestamp=self._last_known_timestamp,
                    is_stale=True,
                    staleness_seconds=age,
                )

        # 4. Sin opciones - Error crítico
        self._failed_fetches += 1
        raise RuntimeError(
            f"❌ No balance available | "
            f"Cache age: {current_time - self._cache_timestamp:.1f}s | "
            f"Max age: {self._max_age}s"
        )

    def _extract_balance(self, balance_data: Dict[str, Any]) -> float:
        """
        Extrae balance de la respuesta del exchange.

        Args:
            balance_data: Respuesta del exchange

        Returns:
            Balance como float

        Raises:
            ValueError: Si no se puede extraer el balance
        """
        if not balance_data:
            raise ValueError("Balance data is empty")

        # Intentar extraer de 'free'
        free_section = balance_data.get("free", {})
        if isinstance(free_section, dict) and self._currency in free_section:
            balance = free_section[self._currency]
            if balance is not None:
                try:
                    return float(balance)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid balance value: {balance}") from e

        # Intentar otras monedas comunes
        for currency in ["USD", "USDT", "USDC", "EUR"]:
            if currency in free_section and free_section[currency] is not None:
                try:
                    balance = float(free_section[currency])
                    self.logger.warning(f"⚠️ Using {currency} instead of {self._currency}")
                    return balance
                except (ValueError, TypeError):
                    continue

        raise ValueError(f"Could not extract balance from: {balance_data}")

    def invalidate(self) -> None:
        """Invalida el cache (fuerza fetch en próxima llamada)."""
        self._cache_timestamp = 0.0
        self.logger.debug("🗑️ Cache invalidated")

    def get_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas del cache."""
        total_requests = self._cache_hits + self._fallback_hits + self._failed_fetches

        return {
            "total_fetches": self._total_fetches,
            "total_requests": total_requests,
            "cache_hits": self._cache_hits,
            "fallback_hits": self._fallback_hits,
            "failed_fetches": self._failed_fetches,
            "cache_hit_rate": self._cache_hits / total_requests if total_requests > 0 else 0,
            "fallback_rate": self._fallback_hits / total_requests if total_requests > 0 else 0,
            "current_age": time.time() - self._cache_timestamp if self._cached_balance else None,
            "is_stale": (time.time() - self._cache_timestamp) > self._cache_ttl if self._cached_balance else True,
        }

    def get_status(self) -> Dict[str, Any]:
        """Obtiene estado actual del cache."""
        current_time = time.time()

        return {
            "cached_balance": self._cached_balance,
            "cache_age": current_time - self._cache_timestamp if self._cached_balance else None,
            "calculated_balance": self._calculated_balance,
            "calculated_age": current_time - self._calculated_timestamp if self._calculated_balance else None,
            "last_known_balance": self._last_known_balance,
            "last_known_age": current_time - self._last_known_timestamp if self._last_known_balance else None,
            "cache_ttl": self._cache_ttl,
            "max_age": self._max_age,
        }
