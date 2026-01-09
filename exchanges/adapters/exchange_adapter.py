"""
ExchangeAdapter - Adaptador Agnóstico para Mesas (DataSource).

Este adaptador envuelve la lógica de negocio del trading y delega
la comunicación con exchanges a conectores modulares específicos.
Es compatible tanto con conectores CCXT como con Native SDKs.

⚠️  ARQUITECTURA MODULAR - IMPORTANTE:
================================================================================
Este adaptador DEBE ser 100% EXCHANGE-AGNOSTIC.
NO agregar lógica específica de ningún exchange aquí.

Arquitectura (v2.0):
    Mesa (DataSource) → ExchangeAdapter (Adaptador) → Conector (Driver) → SDK/CCXT → Exchange

    Ejemplo:
    LiveDataSource → ExchangeAdapter → BinanceNativeConnector → Binance SDK → Binance API

================================================================================

📋 RESPONSABILIDADES DEL ADAPTADOR (ExchangeAdapter):
    ✅ PERMITIDO (Business Logic - Exchange Agnostic):
        - Gestión de balance (BalanceManager)
        - Tracking de posiciones (PositionTracker)
        - Validación de órdenes (límites, balance)
        - Cálculo de precios TP/SL (multipliers → absolute prices)
        - Logging y auditoría
        - Sincronización de estado real (ExchangeStateSync)

    ❌ PROHIBIDO (Exchange-Specific Logic):
        - Lógica específica de Kraken, Binance, etc.
        - Tipos de órdenes específicos de un exchange
        - Parámetros específicos de un exchange
        - Manejo de particularidades de un exchange

📋 RESPONSABILIDADES DEL CONECTOR (KrakenConnector, BinanceNativeConnector, etc.):
    ✅ PERMITIDO (Exchange-Specific Implementation):
        - Comunicación con el exchange (REST + WebSocket)
        - Normalización de datos del exchange
        - Manejo de errores específicos del exchange
        - Rate limiting específico del exchange
        - Implementación de TP/SL según particularidades del exchange
        - Tipos de órdenes específicos (take_profit, stop, etc.)
        - Parámetros específicos (reduceOnly, triggerPrice, etc.)

================================================================================

🔄 FLUJO DE EJECUCIÓN DE ÓRDENES CON TP/SL:

    1. ExchangeAdapter.execute_order(order):
       ├── Validar orden (balance, límites) ← Business logic
       ├── Calcular precios TP/SL absolutos ← Business logic
       │   tp_price = current_price * tp_multiplier
       │   sl_price = current_price * sl_multiplier
       └── Delegar a conector ↓

    2. Connector.create_order_with_tpsl(tp_price, sl_price):
       ├── Kraken: Crear órdenes separadas (take_profit, stop)
       ├── Binance: Agregar TP/SL como params en orden principal
       └── Hyperliquid: Usar su propio mecanismo de TP/SL

    Resultado: Adaptador agnóstico, cada conector maneja sus particularidades

================================================================================

📚 REFERENCIAS:
    - Análisis completo: docs/ARQUITECTURA_MODULARIDAD_ANALISIS.md
    - Interface de conectores: exchanges/connectors/connector_base.py
    - Ejemplo de implementación: exchanges/connectors/binance/binance_native_connector.py

⚠️  ANTES DE MODIFICAR ESTE ARCHIVO:
    1. Pregúntate: ¿Esta lógica es específica de un exchange?
    2. Si SÍ → Debe ir en el conector, NO aquí
    3. Si NO → Puede ir aquí (es business logic)
    4. En duda → Consultar docs/ARQUITECTURA_MODULARIDAD_ANALISIS.md

================================================================================

Usage:
    ```python
    from exchanges.connectors import BinanceNativeConnector
    from exchanges.adapters import ExchangeAdapter

    # Create connector (exchange-specific driver)
    connector = BinanceNativeConnector(mode="demo")

    # Create adapter (exchange-agnostic business logic)
    adapter = ExchangeAdapter(
        connector=connector,
        symbol="BTC/USDT:USDT",
        timeframe="1m"
    )

    # Connect and use
    await adapter.connect()
    candle = await adapter.next_candle()
    result = await adapter.execute_order(order)
    await adapter.close()
    ```
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.network import NetworkIterator, NetworkStatus
from exchanges.connectors.connector_base import BaseConnector


class ExchangeAdapter(NetworkIterator):
    async def fetch_positions(self, symbols: list = None) -> list:
        """
        Fetch open positions, preferring WS if enabled and available.
        """
        cond1 = self.prefer_ws
        cond2 = hasattr(self.connector, "watch_positions")
        cond3 = getattr(self.connector, "enable_websocket", False)

        # Detect WebSocket availability: prefer_ws flag + connector support
        has_ws_api = cond2 and cond3
        ws_available = bool(cond1 and has_ws_api)

        # If symbols is a list of one, pass as string (ccxt.pro expects symbol: str)
        ws_arg = symbols
        if isinstance(symbols, list) and len(symbols) == 1:
            ws_arg = symbols[0]

        if ws_available:
            try:
                if ws_arg is None:
                    return await self.connector.watch_positions()
                else:
                    return await self.connector.watch_positions(ws_arg)
            except NotImplementedError:
                self.logger.info("WS positions not available, falling back to REST.")
            except Exception as e:
                self.logger.error(f"WS positions error (no fallback): {e}")
                raise

        # REST Fallback
        target_symbols = symbols
        if not target_symbols and self.symbol != "MULTI":
            target_symbols = [self.symbol]

        return await self.connector.fetch_positions(target_symbols)

    async def fetch_active_symbols(self) -> List[str]:
        """
        Discover all symbols with activity.
        Delegates to connector.
        """
        return await self.connector.fetch_active_symbols()

    """
    Adaptador agnóstico que envuelve lógica de negocio y delega comunicación a conectores.

    Este adaptador es usado internamente por TestingDataSource y LiveDataSource
    para manejar la lógica de trading (balance, posiciones, TP/SL) mientras
    delega la comunicación con el exchange a conectores específicos.

    Nota Histórica: Originalmente diseñado para CCXT, ahora es agnóstico de SDK.
    Funciona con conectores nativos (BinanceNativeConnector) y CCXT por igual.

    Arquitectura:
        DataSource (Mesa) → ExchangeAdapter (este) → Conector (BinanceNativeConnector, etc.)
    """

    async def fetch_income(
        self,
        symbol: Optional[str] = None,
        income_type: Optional[str] = None,
        since: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetch income history (Funding, Commission, etc.).
        """
        if hasattr(self.connector, "fetch_income"):
            return await self.connector.fetch_income(symbol, income_type, since, limit)
        return []

    async def fetch_balance(self) -> dict:
        """
        Fetch account balance, preferring WS if enabled and available.
        """
        if self.prefer_ws and hasattr(self.connector, "watch_balance"):
            try:
                return await self.connector.watch_balance()
            except NotImplementedError:
                self.logger.info("WS balance not available, falling back to REST.")
            except Exception as e:
                self.logger.error(f"WS balance error: {e}, falling back to REST.")
        return await self.connector.fetch_balance()

    def __init__(
        self,
        connector: BaseConnector,
        symbol: str,
        timeframe: str = "1m",
        prefer_ws: bool = False,
    ):
        super().__init__()
        # El conector es la única dependencia.
        self.connector = connector

        # Configuración básica de operación
        self.symbol = symbol
        self.timeframe = timeframe
        self.prefer_ws = prefer_ws

        # Logger setup
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.info(f"ExchangeAdapter initialized | Symbol: {self.symbol} | Timeframe: {self.timeframe}")

        # El adapter es sin estado, solo delega. La instancia de exchange se obtiene del conector.
        self.exchange = getattr(self.connector, "exchange", None)
        if not self.exchange:
            self.logger.info("⚠️ Connector does not expose 'exchange' attribute (Virtual/Simulated?).")

    async def connect(self) -> None:
        """Connect the underlying connector if it provides a connect method.

        This method should be called before any data fetching operations.
        """
        if hasattr(self.connector, "connect"):
            await self.connector.connect()
        else:
            self.logger.warning("Connector does not implement async connect().")

    # duplicate fetch_positions block removed

    async def fetch_order_book(self, symbol: str = None, limit: int = 20) -> Dict[str, Any]:
        """
        Fetch order book, preferring WS if enabled and available.
        """
        symbol = symbol or self.symbol
        if self.prefer_ws and hasattr(self.connector, "watch_order_book"):
            try:
                return await self.connector.watch_order_book(symbol, limit)
            except NotImplementedError:
                self.logger.info("WS order book not available, falling back to REST.")
            except Exception as e:
                self.logger.error(f"WS order book error: {e}, falling back to REST.")
        return await self.connector.fetch_order_book(symbol, limit)

    async def watch_ticker(self, symbol: str = None) -> Dict[str, Any]:
        """
        Watch ticker using WebSocket (if supported).
        """
        symbol = symbol or self.symbol
        if hasattr(self.connector, "watch_ticker"):
            return await self.connector.watch_ticker(symbol)
        raise NotImplementedError("Connector does not support watch_ticker")

    async def watch_order_book(self, symbol: str = None, limit: int = 20) -> Dict[str, Any]:
        """
        Watch order book using WebSocket (if supported).
        """
        symbol = symbol or self.symbol
        if hasattr(self.connector, "watch_order_book"):
            return await self.connector.watch_order_book(symbol, limit)
        raise NotImplementedError("Connector does not support watch_order_book")

    async def watch_trades(self, symbol: str = None) -> Dict[str, Any]:
        """
        Watch trades using WebSocket (if supported).
        """
        symbol = symbol or self.symbol
        if hasattr(self.connector, "watch_trades"):
            return await self.connector.watch_trades(symbol)
        raise NotImplementedError("Connector does not support watch_trades")

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch 24hr ticker for a symbol."""
        return await self.connector.fetch_ticker(symbol)

    async def fetch_tickers(self) -> Dict[str, Dict[str, Any]]:
        """Fetch all 24hr tickers (Bulk)."""
        return await self.connector.fetch_tickers()

    async def fetch_book_tickers(self) -> Dict[str, Dict[str, float]]:
        """Fetch all book tickers (Bulk)."""
        if hasattr(self.connector, "fetch_book_tickers"):
            return await self.connector.fetch_book_tickers()
        return {}

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to exchange format."""
        return self.connector.normalize_symbol(symbol)

    def denormalize_symbol(self, symbol: str) -> str:
        """Denormalize symbol to unified format."""
        return self.connector.denormalize_symbol(symbol)

    async def get_current_price(self, symbol: str = None) -> float:
        """
        Get current market price for a symbol (async).

        Args:
            symbol: Trading symbol (uses self.symbol if not provided)

        Returns:
            Current price as float

        Raises:
            RuntimeError: If not connected
            ValueError: If price cannot be obtained
        """
        symbol = symbol or self.symbol
        self.logger.info(f"🔍 get_current_price | requested_symbol={symbol} | adapter_symbol={self.symbol}")

        try:
            # Obtener ticker del exchange (async)
            ticker = await self.connector.fetch_ticker(symbol)
            current_price = ticker.get("last")

            # Validar que el precio sea válido (no None, no 0, no negativo)
            if current_price is None or current_price == 0 or current_price < 0:
                # Intentar con "close" como fallback
                current_price = ticker.get("close")
                if current_price is None or current_price == 0 or current_price < 0:
                    # Intentar con "bid" como último recurso
                    current_price = ticker.get("bid")
                    if current_price is None or current_price == 0 or current_price < 0:
                        raise ValueError(f"No valid price data available for {symbol}. Ticker: {ticker}")

            current_price = float(current_price)
            self.logger.info(f"💰 Current price for {symbol}: {current_price}")
            return current_price

        except Exception as e:
            self.logger.error(f"❌ Error getting current price for {symbol}: {e}")
            raise ValueError(f"Cannot get current price for {symbol}: {e}")

    @property
    def supports_native_oco(self) -> bool:
        """Determines if the underlying connector supports native OCO."""
        # Forcing False to prioritize hardened Manual OCO orchestration
        return False

    async def register_oco_pair(self, symbol: str, tp_order_id: str, sl_order_id: str):
        """
        Registers an OCO pair with the underlying connector if supported.
        Used for manual OCO orchestration.
        """
        if hasattr(self.connector, "register_oco_pair"):
            await self.connector.register_oco_pair(symbol, tp_order_id, sl_order_id)

    # =========================================================
    # 📊 MARKET DATA
    # =========================================================

    async def next_candle(self) -> Optional[Dict]:
        """
        Obtiene la siguiente vela del exchange. No gestiona estado.
        Falla rápido si el conector no devuelve datos.
        """
        candles = await self.connector.fetch_ohlcv(self.symbol, self.timeframe, limit=1)
        if not candles:
            return None

        raw_candle = candles[0]
        candle_dict = {
            "timestamp": raw_candle[0],
            "open": raw_candle[1],
            "high": raw_candle[2],
            "low": raw_candle[3],
            "close": raw_candle[4],
            "volume": raw_candle[5],
        }
        self._last_candle = candle_dict
        return candle_dict

    # =========================================================
    # 📝 ORDER EXECUTION
    # =========================================================

    async def execute_order(self, order: Dict) -> Dict:
        """
        Ejecuta una orden en el exchange.

        Nota: OCO Manual es responsabilidad de Croupier.
        Este adapter solo crea órdenes individuales.
        """
        try:
            # Traducir formato de Croupier a CCXT si es necesario
            if order.get("side") in ["LONG", "SHORT"]:
                order = order.copy()
                order["side"] = "buy" if order["side"] == "LONG" else "sell"

            # Todas las órdenes van por el mismo camino
            # Execute order via connector
            # Note: optional WS-confirmation flags may be present in `order` but
            # are not used by the generic adapter implementation.

            # Map 'type' to 'order_type' for connector compatibility
            order_copy = order.copy()
            order_type = order_copy.pop("type", "market")

            # Remove Croupier-specific parameters that connectors don't accept
            # Use explicit arguments to avoid passing unsupported kwargs (like stop_price)
            result = await self.connector.create_order(
                symbol=order_copy["symbol"],
                side=order_copy["side"],
                amount=order_copy["amount"],
                price=order_copy.get("price"),
                order_type=order_type,
                params=order_copy.get("params"),
            )
            return result
        except Exception as e:
            self.logger.error(f"❌ Error executing order: {e}")
            raise

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza un trade usando la implementación específica del connector.

        Args:
            raw_trade: Trade en formato crudo del exchange

        Returns:
            Trade normalizado con campos adicionales:
            - is_close: bool - Si es un cierre de posición
            - realized_pnl: float - PnL realizado (si es cierre)
            - close_reason: str - Razón del cierre ("TP", "SL", "MANUAL", etc.)
        """
        if hasattr(self.connector, "normalize_trade"):
            return self.connector.normalize_trade(raw_trade)
        else:
            # Fallback agnóstico si el connector no implementa normalize_trade
            return {**raw_trade, "is_close": False, "realized_pnl": 0.0, "close_reason": None}

    async def calculate_tpsl_prices(
        self, order: Dict, entry_price: Optional[float] = None
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Calcula los precios absolutos de TP/SL a partir de porcentajes.

        Args:
            order: Diccionario de la orden. Debe contener:
                   - symbol: Símbolo del par
                   - side: 'buy' (LONG) o 'sell' (SHORT)
                   - take_profit: Porcentaje de TP (ej: 0.01 para 1%)
                   - stop_loss: Porcentaje de SL (ej: 0.01 para 1%)
            entry_price: Precio de entrada (opcional). Si no se da, se busca el actual.

        Returns:
            Tuple (tp_price, sl_price)
        """
        if "take_profit" not in order or "stop_loss" not in order:
            return None, None

        try:
            if entry_price is None or entry_price <= 0:
                current_price = await self.get_current_price(order.get("symbol", self.symbol))
            else:
                current_price = entry_price

            # Asumimos que vienen como porcentajes (ej: 0.01)
            tp_pct = float(order["take_profit"])
            sl_pct = float(order["stop_loss"])

            # Validación de seguridad: si parecen multiplicadores (ej: > 0.5), advertir o convertir
            # Pero para limpiar la arquitectura, asumiremos que el caller (Gemini) ya se actualizó.
            # Si alguien manda 1.01 pensando que es 1%, obtendrá un TP de +101% (aceptable error de usuario)
            # Si manda 1.01 pensando que es precio, fallará la lógica de porcentaje.

            safety_margin_factor = 0.0005  # 0.05% de margen extra para asegurar ejecución

            side = order.get("side", "").lower()
            if side in ["buy", "long"]:  # LONG
                # TP arriba, SL abajo
                tp_price = current_price * (1 + tp_pct)
                sl_price = current_price * (1 - sl_pct) * (1 - safety_margin_factor)
            else:  # SHORT
                # TP abajo, SL arriba
                tp_price = current_price * (1 - tp_pct)
                sl_price = current_price * (1 + sl_pct) * (1 + safety_margin_factor)

            return tp_price, sl_price
        except Exception as e:
            self.logger.error(f"❌ Error calculando precios TP/SL: {e}")
            raise

    # =========================================================
    # 📋 ORDER MANAGEMENT (Added for component abstraction)
    # =========================================================

    async def fetch_order(self, order_id: str, symbol: str = None) -> Dict[str, Any]:
        """
        Fetch order status from exchange.

        Args:
            order_id: Order ID to fetch
            symbol: Trading symbol (uses self.symbol if not provided)

        Returns:
            Order dict with status, filled amount, etc.
        """
        symbol = symbol or self.symbol
        return await self.connector.fetch_order(order_id, symbol)

    async def cancel_order(self, order_id: str, symbol: str = None) -> Dict[str, Any]:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel
            symbol: Trading symbol (uses self.symbol if not provided)

        Returns:
            Cancellation result
        """
        symbol = symbol or self.symbol
        return await self.connector.cancel_order(order_id, symbol)

    async def amend_order(
        self,
        symbol: str,
        order_id: str,
        side: str,
        quantity: float = None,
        price: float = None,
        params: Dict[str, Any] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Amend an existing order by delegating to the connector.
        """
        if hasattr(self.connector, "amend_order"):
            return await self.connector.amend_order(
                symbol=symbol,
                order_id=order_id,
                side=side,
                quantity=quantity,
                price=price,
                params=params,
                timeout=timeout,
            )
        raise NotImplementedError(f"Connector {self.connector.__class__.__name__} does not support amend_order")

    async def cancel_all_orders(self, symbol: str = None) -> None:
        """
        Cancel ALL open orders for a symbol.
        """
        symbol = symbol or self.symbol
        if hasattr(self.connector, "cancel_all_orders"):
            await self.connector.cancel_all_orders(symbol)
        else:
            # Fallback: Individual cancellation (Slow)
            orders = await self.connector.fetch_open_orders(symbol)
            for o in orders:
                await self.connector.cancel_order(o["id"], symbol)

    async def create_market_order(
        self, symbol: str, side: str, amount: float, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a simple market order (for reconciliation/cleanup).

        Args:
            symbol: Trading symbol
            side: "buy" or "sell"
            amount: Order amount
            params: Optional extra parameters (e.g. reduceOnly)

        Returns:
            Order result
        """
        return await self.connector.create_market_order(symbol=symbol, side=side, amount=amount, params=params)

    async def fetch_open_orders(self, symbol: str = None) -> list:
        """
        Fetch all open orders for a symbol.

        Args:
            symbol: Trading symbol (uses self.symbol if not provided)

        Returns:
            List of open orders
        """
        if not symbol and self.symbol != "MULTI":
            symbol = self.symbol
        return await self.connector.fetch_open_orders(symbol)

    async def fetch_my_trades(self, symbol: str = None, since: int = None, limit: int = 100) -> list:
        """
        Fetch user's trade history.

        Args:
            symbol: Trading symbol (uses self.symbol if not provided)
            since: Timestamp in ms
            limit: Num trades

        Returns:
            List of trades
        """
        if not symbol and self.symbol != "MULTI":
            symbol = self.symbol
        if hasattr(self.connector, "fetch_my_trades"):
            return await self.connector.fetch_my_trades(symbol, since, limit)
        # Fallback empty list if not supported? Or raise?
        # Reconciliation depends on this, so better to return empty than crash if missing logic
        self.logger.warning(f"Connector {self.exchange_name} does not support fetch_my_trades")
        return []

    async def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
    ) -> Dict[str, Any]:
        """
        Create a stop loss order.

        Used by ExitManager for breakeven/trailing stop modifications.

        Args:
            symbol: Trading symbol
            side: "buy" or "sell" (opposite of position side)
            amount: Order amount
            stop_price: Stop trigger price

        Returns:
            Order result with id
        """
        # Delegate to connector's create_order with stop_market type
        return await self.connector.create_order(
            symbol=symbol,
            side=side,
            amount=amount,
            price=None,
            order_type="stop_market",
            params={"stopPrice": stop_price, "reduceOnly": True},
        )

    # =========================================================
    # 📊 PROPERTIES
    # =========================================================

    @property
    def exchange_name(self) -> str:
        """Get exchange name."""
        return self.connector.exchange_name

    async def disconnect(self) -> None:
        """
        Desconecta el adaptador y su conector subyacente.
        """
        if hasattr(self.connector, "close"):
            await self.connector.close()

    def price_to_precision(self, symbol: str, price: float) -> str:
        """
        Format price to symbol precision.
        """
        if hasattr(self.connector, "price_to_precision"):
            return self.connector.price_to_precision(symbol, price)
        # Fallback to exchange object if available (CCXT)
        if self.exchange and hasattr(self.exchange, "price_to_precision"):
            return self.exchange.price_to_precision(symbol, price)
        return str(price)

    def set_precision_profile(self, profile: dict):
        """
        Store precision profile built during flytest.
        Used for optimal order sizing without runtime lookups.
        """
        self._precision_profile = profile

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """
        Format amount to symbol precision.
        Uses precision profile from flytest if available (optimal path).
        """
        # Priority 1: Use pre-loaded precision profile from flytest
        if hasattr(self, "_precision_profile") and self._precision_profile:
            if symbol in self._precision_profile:
                step_size = self._precision_profile[symbol].get("step_size", 0.001)
                rounded = round(amount / step_size) * step_size
                decimals = self._precision_profile[symbol].get("decimals", 3)
                return f"{rounded:.{decimals}f}"

        # Priority 2: Delegate to connector
        if hasattr(self.connector, "amount_to_precision"):
            return self.connector.amount_to_precision(symbol, amount)

        # Priority 3: Fallback to exchange object if available (CCXT)
        if self.exchange and hasattr(self.exchange, "amount_to_precision"):
            return self.exchange.amount_to_precision(symbol, amount)

        return str(amount)

    # =========================================================
    # 🕵️ V4 NETWORK ITERATOR IMPLEMENTATION
    # =========================================================

    @property
    def name(self) -> str:
        return f"Adapter({self.exchange_name})"

    async def start(self) -> None:
        """Start the adapter (connect)."""
        self._network_status = NetworkStatus.STARTING
        try:
            await self.connect()
            self._network_status = NetworkStatus.CONNECTED
        except Exception as e:
            self.logger.error(f"❌ Failed to start adapter: {e}")
            self._network_status = NetworkStatus.ERROR

    async def stop(self) -> None:
        """Stop the adapter."""
        await self.disconnect()
        self._network_status = NetworkStatus.STOPPED

    async def tick(self, timestamp: float) -> None:
        """
        Clock tick handler.
        Checks connection health periodically.
        """
        # Simple Polling for status update (Frequency controlled here, not sleep)
        if int(timestamp) % 5 == 0:  # Check every 5 seconds
            await self.check_network()

    async def check_network(self) -> NetworkStatus:
        """Check connection status from connector."""
        if hasattr(self.connector, "is_connected"):
            # Check property directly
            is_connected = self.connector.is_connected
            # Special case: connector might be a coroutine property (unlikely but possible in some designs)
            if hasattr(is_connected, "__await__"):
                is_connected = await is_connected

            if is_connected:
                self._network_status = NetworkStatus.CONNECTED
            else:
                self._network_status = NetworkStatus.NOT_CONNECTED

        return self._network_status
