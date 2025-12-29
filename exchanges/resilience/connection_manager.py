"""
ConnectionManager - Gestión robusta de conexiones con WebSocket + REST fallback.

Este módulo implementa:
- WebSocket como conexión primaria (CCXT Pro)
- REST como fallback automático
- Reconexión automática con exponential backoff
- Circuit breaker pattern
- Health checks periódicos
- Métricas de conexión

Author: Casino V3 Team
Version: 2.0.0
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import ccxt
import ccxt.pro as ccxtpro


class ConnectionState(Enum):
    """Estados de la conexión."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED_WS = "connected_websocket"
    CONNECTED_REST = "connected_rest"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class CircuitState(Enum):
    """Estados del circuit breaker."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Too many failures, stop trying
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class ConnectionMetrics:
    """Métricas de conexión."""

    ws_connections: int = 0
    ws_disconnections: int = 0
    ws_errors: int = 0
    rest_fallbacks: int = 0
    rest_errors: int = 0
    total_reconnections: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    uptime_start: float = 0.0

    def uptime_seconds(self) -> float:
        """Calcula el uptime en segundos."""
        if self.uptime_start == 0:
            return 0.0
        return time.time() - self.uptime_start


class ConnectionManager:
    """
    Gestiona conexiones robustas con WebSocket + REST fallback.

    Features:
    - WebSocket primario (tiempo real, bajo latency)
    - REST fallback automático si WebSocket falla
    - Reconexión automática con exponential backoff
    - Circuit breaker para evitar reconexiones infinitas
    - Health checks periódicos
    - Métricas detalladas

    Usage:
        ```python
        manager = ConnectionManager(
            exchange_class=ccxtpro.krakenfutures,
            config={'apiKey': '...', 'secret': '...'}
        )

        await manager.connect()

        # Use WebSocket (preferred) or REST (fallback)
        ticker = await manager.fetch_ticker('BTC/USD')

        # Cleanup
        await manager.close()
        ```
    """

    def __init__(
        self,
        exchange_class: type,
        config: Dict[str, Any],
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        circuit_threshold: int = 10,
        circuit_timeout: float = 300.0,
    ):
        """
        Initialize ConnectionManager.

        Args:
            exchange_class: CCXT Pro exchange class (e.g., ccxtpro.krakenfutures)
            config: Exchange configuration (API keys, testnet, etc.)
            max_retries: Maximum reconnection attempts before giving up
            base_delay: Base delay for exponential backoff (seconds)
            max_delay: Maximum delay between retries (seconds)
            circuit_threshold: Failures before opening circuit breaker
            circuit_timeout: Seconds to wait before trying half-open state
        """
        self.logger = logging.getLogger("ConnectionManager")

        # Exchange configuration
        self.exchange_class = exchange_class
        self.config = config

        # Connections
        self.ws_exchange: Optional[ccxtpro.Exchange] = None
        self.rest_exchange: Optional[ccxt.Exchange] = None

        # State
        self.state = ConnectionState.DISCONNECTED
        self.circuit_state = CircuitState.CLOSED

        # Retry configuration
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retry_count = 0

        # Circuit breaker configuration
        self.circuit_threshold = circuit_threshold
        self.circuit_timeout = circuit_timeout
        self.circuit_failures = 0
        self.circuit_opened_at: Optional[float] = None

        # Metrics
        self.metrics = ConnectionMetrics()

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval = 60.0  # seconds

        # Reconnection task
        self._reconnect_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """
        Establece conexión con el exchange.

        Intenta WebSocket primero, fallback a REST si falla.

        Returns:
            True si la conexión fue exitosa, False en caso contrario
        """
        if self.state in [ConnectionState.CONNECTED_WS, ConnectionState.CONNECTED_REST]:
            self.logger.info("Ya conectado")
            return True

        self.state = ConnectionState.CONNECTING
        self.metrics.uptime_start = time.time()

        # Try WebSocket first
        if await self._connect_websocket():
            self.state = ConnectionState.CONNECTED_WS
            self.logger.info("✅ Conectado via WebSocket")

            # Start health check
            self._start_health_check()
            return True

        # Fallback to REST
        self.logger.warning("⚠️ WebSocket falló, usando REST fallback")
        if await self._connect_rest():
            self.state = ConnectionState.CONNECTED_REST
            self.metrics.rest_fallbacks += 1
            self.logger.info("✅ Conectado via REST (fallback)")

            # Try to reconnect to WebSocket in background
            self._start_reconnect_task()
            return True

        # Both failed
        self.state = ConnectionState.FAILED
        self.logger.error("❌ Falló conexión WebSocket y REST")
        return False

    async def _connect_websocket(self) -> bool:
        """Intenta conectar via WebSocket (CCXT Pro)."""
        try:
            self.ws_exchange = self.exchange_class(self.config)

            # Test connection with a simple call
            await asyncio.wait_for(self.ws_exchange.load_markets(), timeout=10.0)

            self.metrics.ws_connections += 1
            self.retry_count = 0  # Reset retry counter on success
            self._reset_circuit_breaker()
            return True

        except asyncio.TimeoutError:
            self.logger.error("❌ WebSocket timeout")
            self._record_failure("WebSocket timeout")
            return False

        except Exception as e:
            self.logger.error(f"❌ WebSocket error: {e}")
            self._record_failure(f"WebSocket error: {e}")

            if self.ws_exchange:
                try:
                    await self.ws_exchange.close()
                except Exception:
                    pass
                self.ws_exchange = None

            return False

    async def _connect_rest(self) -> bool:
        """Intenta conectar via REST (CCXT estándar)."""
        try:
            # Import standard ccxt (not pro)
            import ccxt

            # Get the standard exchange class
            exchange_name = self.exchange_class.id
            rest_class = getattr(ccxt, exchange_name)

            self.rest_exchange = rest_class(self.config)

            # Test connection
            await asyncio.wait_for(self.rest_exchange.load_markets(), timeout=10.0)

            return True

        except asyncio.TimeoutError:
            self.logger.error("❌ REST timeout")
            self._record_failure("REST timeout")
            return False

        except Exception as e:
            self.logger.error(f"❌ REST error: {e}")
            self._record_failure(f"REST error: {e}")

            if self.rest_exchange:
                try:
                    await self.rest_exchange.close()
                except Exception:
                    pass
                self.rest_exchange = None

            return False

    def _record_failure(self, error: str):
        """Registra un fallo y actualiza circuit breaker."""
        self.metrics.last_error = error
        self.metrics.last_error_time = time.time()
        self.circuit_failures += 1

        # Check if we should open circuit breaker
        if self.circuit_failures >= self.circuit_threshold:
            self._open_circuit_breaker()

    def _open_circuit_breaker(self):
        """Abre el circuit breaker (deja de intentar reconexiones)."""
        if self.circuit_state != CircuitState.OPEN:
            self.circuit_state = CircuitState.OPEN
            self.circuit_opened_at = time.time()
            self.logger.error(
                f"🔴 Circuit breaker ABIERTO después de {self.circuit_failures} fallos. "
                f"Esperando {self.circuit_timeout}s antes de reintentar."
            )

    def _reset_circuit_breaker(self):
        """Resetea el circuit breaker después de una conexión exitosa."""
        if self.circuit_state != CircuitState.CLOSED:
            self.logger.info("🟢 Circuit breaker CERRADO - conexión restaurada")

        self.circuit_state = CircuitState.CLOSED
        self.circuit_failures = 0
        self.circuit_opened_at = None

    def _can_retry(self) -> bool:
        """Verifica si podemos reintentar la conexión."""
        # Check circuit breaker
        if self.circuit_state == CircuitState.OPEN:
            if self.circuit_opened_at is None:
                return False

            # Check if timeout has passed
            elapsed = time.time() - self.circuit_opened_at
            if elapsed < self.circuit_timeout:
                return False

            # Move to half-open state (allow one retry)
            self.circuit_state = CircuitState.HALF_OPEN
            self.logger.info("🟡 Circuit breaker HALF-OPEN - intentando reconexión")

        return True

    async def _reconnect_websocket(self):
        """Intenta reconectar a WebSocket en background."""
        while self.state == ConnectionState.CONNECTED_REST:
            if not self._can_retry():
                await asyncio.sleep(10.0)
                continue

            self.logger.info("🔄 Intentando reconectar a WebSocket...")

            if await self._connect_websocket():
                # Success! Switch from REST to WebSocket
                self.state = ConnectionState.CONNECTED_WS
                self.logger.info("✅ Reconectado a WebSocket")

                # Close REST connection
                if self.rest_exchange:
                    try:
                        await self.rest_exchange.close()
                    except Exception:
                        pass
                    self.rest_exchange = None

                # Start health check
                self._start_health_check()
                break

            # Calculate backoff delay
            delay = min(self.base_delay * (2**self.retry_count), self.max_delay)
            self.retry_count += 1
            self.metrics.total_reconnections += 1

            self.logger.info(f"⏳ Reintentando en {delay:.1f}s...")
            await asyncio.sleep(delay)

    def _start_reconnect_task(self):
        """Inicia tarea de reconexión en background."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_websocket())

    async def _health_check_loop(self):
        """Loop de health checks periódicos."""
        while self.state == ConnectionState.CONNECTED_WS:
            await asyncio.sleep(self._health_check_interval)

            try:
                # Simple health check: fetch ticker
                if self.ws_exchange:
                    await asyncio.wait_for(self.ws_exchange.fetch_ticker("BTC/USD"), timeout=5.0)
                    self.logger.debug("✅ Health check OK")

            except Exception as e:
                self.logger.warning(f"⚠️ Health check falló: {e}")
                self.metrics.ws_errors += 1

                # Try to reconnect
                self.state = ConnectionState.RECONNECTING
                self.metrics.ws_disconnections += 1

                if not await self._connect_websocket():
                    # WebSocket failed, fallback to REST
                    self.logger.warning("⚠️ WebSocket falló en health check, usando REST")
                    if await self._connect_rest():
                        self.state = ConnectionState.CONNECTED_REST
                        self.metrics.rest_fallbacks += 1
                        self._start_reconnect_task()
                    else:
                        self.state = ConnectionState.FAILED
                        break
                else:
                    self.state = ConnectionState.CONNECTED_WS

    def _start_health_check(self):
        """Inicia health checks periódicos."""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch ticker usando WebSocket o REST fallback.

        Args:
            symbol: Trading pair symbol

        Returns:
            Ticker data
        """
        if self.state == ConnectionState.CONNECTED_WS and self.ws_exchange:
            try:
                return await self.ws_exchange.fetch_ticker(symbol)
            except Exception as e:
                self.logger.warning(f"⚠️ WebSocket fetch_ticker falló: {e}, usando REST")
                self.metrics.ws_errors += 1
                # Fallback to REST

        if self.rest_exchange:
            try:
                return await self.rest_exchange.fetch_ticker(symbol)
            except Exception as e:
                self.logger.error(f"❌ REST fetch_ticker falló: {e}")
                self.metrics.rest_errors += 1
                raise

        raise RuntimeError("No hay conexión disponible")

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: Optional[int] = None) -> list:
        """
        Fetch OHLCV usando WebSocket o REST fallback.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe (e.g., '1m', '5m')
            limit: Number of candles

        Returns:
            OHLCV data
        """
        if self.state == ConnectionState.CONNECTED_WS and self.ws_exchange:
            try:
                return await self.ws_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            except Exception as e:
                self.logger.warning(f"⚠️ WebSocket fetch_ohlcv falló: {e}, usando REST")
                self.metrics.ws_errors += 1
                # Fallback to REST

        if self.rest_exchange:
            try:
                return await self.rest_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            except Exception as e:
                self.logger.error(f"❌ REST fetch_ohlcv falló: {e}")
                self.metrics.rest_errors += 1
                raise

        raise RuntimeError("No hay conexión disponible")

    # ----------------------------
    # New WS-first helper APIs (stubs / safe defaults)
    # ----------------------------
    async def ensure_ws_connected(self) -> bool:
        """
        Garantiza que exista una conexión WebSocket activa.

        Si ya está conectada, retorna True. Si no, intenta conectar via
        WebSocket y retorna True/False según el resultado.
        """
        if self.state == ConnectionState.CONNECTED_WS and self.ws_exchange:
            return True

        # Try to connect via websocket
        ok = await self._connect_websocket()
        if ok:
            self.state = ConnectionState.CONNECTED_WS
            self._start_health_check()
            return True

        return False

    async def watch_orders(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        """
        Wrapper para `ws_exchange.watch_orders(...)`.

        Retorna la lista de órdenes/actualizaciones desde el WebSocket si está
        disponible; si no está, levanta RuntimeError para que el caller use
        fallback REST.
        """
        if not (self.state == ConnectionState.CONNECTED_WS and self.ws_exchange):
            raise RuntimeError("WebSocket no conectado; no es posible watch_orders")

        # Default params
        params = params or {}

        # Delegate to ccxt.pro implementation
        try:
            return await self.ws_exchange.watch_orders(symbol, since, limit, params)
        except Exception as e:
            self.logger.warning(f"⚠️ watch_orders error: {e}")
            self.metrics.ws_errors += 1
            raise

    async def watch_my_trades(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        """
        Wrapper para `ws_exchange.watch_my_trades(...)`.

        Provee las actualizaciones de trades del usuario (fills) vía WebSocket.
        """
        if not (self.state == ConnectionState.CONNECTED_WS and self.ws_exchange):
            raise RuntimeError("WebSocket no conectado; no es posible watch_my_trades")

        params = params or {}
        try:
            return await self.ws_exchange.watch_my_trades(symbol, since, limit, params)
        except Exception as e:
            self.logger.warning(f"⚠️ watch_my_trades error: {e}")
            self.metrics.ws_errors += 1
            raise

    def is_ws_primary(self) -> bool:
        """
        Indica si la conexión primaria actualmente es WebSocket.
        """
        return self.state == ConnectionState.CONNECTED_WS and self.ws_exchange is not None

    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas de conexión."""
        return {
            "state": self.state.value,
            "circuit_state": self.circuit_state.value,
            "uptime_seconds": self.metrics.uptime_seconds(),
            "ws_connections": self.metrics.ws_connections,
            "ws_disconnections": self.metrics.ws_disconnections,
            "ws_errors": self.metrics.ws_errors,
            "rest_fallbacks": self.metrics.rest_fallbacks,
            "rest_errors": self.metrics.rest_errors,
            "total_reconnections": self.metrics.total_reconnections,
            "last_error": self.metrics.last_error,
            "last_error_time": self.metrics.last_error_time,
        }

    async def close(self):
        """Cierra todas las conexiones."""
        self.logger.info("🔌 Cerrando conexiones...")

        # Cancel tasks
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # Close exchanges
        if self.ws_exchange:
            try:
                await self.ws_exchange.close()
            except Exception as e:
                self.logger.error(f"Error cerrando WebSocket: {e}")

        if self.rest_exchange:
            try:
                await self.rest_exchange.close()
            except Exception as e:
                self.logger.error(f"Error cerrando REST: {e}")

        self.state = ConnectionState.DISCONNECTED
        self.logger.info("✅ Conexiones cerradas")
