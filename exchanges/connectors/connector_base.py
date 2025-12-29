"""
Base Connector Interface for Exchange Integration.

This module defines the abstract base class that all exchange connectors must implement.
Inspired by Hummingbot's connector architecture.

⚠️  ARQUITECTURA MODULAR - IMPORTANTE:
================================================================================
Los conectores DEBEN manejar TODAS las particularidades específicas del exchange.
El adaptador (CCXTAdapter) NO debe conocer detalles de ningún exchange.

Arquitectura (v2.0):
    CCXTAdapter (Adaptador) → BaseConnector (Interface) → KrakenConnector (Implementation)
                                                        → BinanceConnector (Implementation)
                                                        → HyperliquidConnector (Implementation)

================================================================================

📋 PRINCIPIOS ARQUITECTURALES:

    1. SEPARACIÓN DE RESPONSABILIDADES:
       ├── Adaptador (CCXTAdapter): Business logic exchange-agnostic
       └── Conector (este): Comunicación y particularidades del exchange

    2. INTERFAZ ESTANDARIZADA:
       ├── Todos los exchanges implementan los mismos métodos
       └── Pero cada uno con su propia implementación específica

    3. NORMALIZACIÓN:
       ├── Cada conector normaliza respuestas del exchange
       └── Formato común para que el adaptador sea agnóstico

    4. MANEJO DE PARTICULARIDADES:
       ├── TP/SL: Cada exchange tiene su propio mecanismo
       ├── Tipos de órdenes: Específicos de cada exchange
       └── Parámetros: Específicos de cada exchange

================================================================================

📋 RESPONSABILIDADES DEL CONECTOR:

    ✅ DEBE IMPLEMENTAR (Exchange-Specific):
        - Conexión al exchange (REST + WebSocket)
        - Fetch de datos de mercado (OHLCV, order book, ticker)
        - Ejecución de órdenes con particularidades del exchange
        - Fetch de datos de cuenta (balance, posiciones, trades)
        - Normalización de respuestas a formato común
        - Manejo de errores específicos del exchange
        - Rate limiting específico del exchange
        - Implementación de TP/SL según el exchange:
          * Kraken: Órdenes separadas (take_profit, stop)
          * Binance: Params en orden principal
          * Hyperliquid: Su propio mecanismo

    ❌ NO DEBE HACER:
        - Lógica de negocio (va en el adaptador)
        - Gestión de balance (va en BalanceManager)
        - Tracking de posiciones (va en PositionTracker)
        - Validación de órdenes (va en el adaptador)

================================================================================

🔄 FLUJO DE IMPLEMENTACIÓN DE TP/SL (EJEMPLO CLAVE):

    BaseConnector (Interface):
        @abstractmethod
        async def create_order_with_tpsl(tp_price, sl_price):
            pass

    KrakenConnector (Implementation):
        async def create_order_with_tpsl(tp_price, sl_price):
            # 1. Crear orden principal
            main_order = await self.create_order(...)
            # 2. Crear TP como conditional order (Kraken-specific)
            await self.create_order(order_type="take_profit", ...)
            # 3. Crear SL como stop order (Kraken-specific)
            await self.create_order(order_type="stop", ...)
            return main_order

    BinanceConnector (Implementation):
        async def create_order_with_tpsl(tp_price, sl_price):
            # Binance permite TP/SL como params en la orden principal
            params = {"stopPrice": tp_price, "stopLoss": sl_price}
            return await self.create_order(..., params=params)

    Resultado: Cada exchange maneja TP/SL a su manera, adaptador no lo sabe

================================================================================

📚 REFERENCIAS:
    - Análisis completo: docs/ARQUITECTURA_MODULARIDAD_ANALISIS.md
    - Adaptador agnóstico: exchanges/adapters/exchange_adapter.py
    - Ejemplo de implementación: exchanges/connectors/binance/binance_native_connector.py

⚠️  AL IMPLEMENTAR UN NUEVO CONECTOR:
    1. Heredar de BaseConnector
    2. Implementar TODOS los métodos abstractos
    3. Manejar TODAS las particularidades del exchange aquí
    4. NO agregar lógica específica en el adaptador
    5. Normalizar respuestas a formato común

================================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseConnector(ABC):
    """
    Abstract base class for exchange connectors.

    All exchange connectors (Kraken, Binance, Hyperliquid, etc.) must inherit from this class
    and implement all abstract methods.

    Responsibilities:
        - Connect to exchange (REST + WebSocket)
        - Fetch market data (OHLCV, order book)
        - Execute orders
        - Fetch account data (balance, positions)
        - Normalize exchange-specific responses to common format
        - Handle exchange-specific errors and rate limits

    Example:
        ```python
        class KrakenConnector(BaseConnector):
            async def connect(self):
                # Kraken-specific connection logic
                pass

            async def fetch_ohlcv(self, symbol, timeframe, limit):
                # Kraken-specific OHLCV fetching
                pass
        ```
    """

    # =========================================================
    # 🔌 CONNECTION MANAGEMENT
    # =========================================================

    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to the exchange.

        This method should:
            1. Initialize CCXT exchange instance
            2. Configure API URLs (testnet/mainnet)
            3. Load markets
            4. Setup WebSocket connections (if enabled)
            5. Authenticate with API keys

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If API keys are invalid

        Example:
            ```python
            connector = KrakenConnector(api_key, secret, testnet=True)
            await connector.connect()
            ```
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close all connections to the exchange.

        This method should:
            1. Close WebSocket connections
            2. Close CCXT exchange instance
            3. Clean up resources

        Example:
            ```python
            await connector.close()
            ```
        """
        pass

    # =========================================================
    # 📊 MARKET DATA
    # =========================================================

    @abstractmethod
    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV (candlestick) data from the exchange.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USD", "ETH/USDT")
            timeframe: Candle timeframe (e.g., "1m", "5m", "1h", "1d")
            limit: Number of candles to fetch (default: 100)

        Returns:
            List of normalized candle dictionaries:
            ```python
            [
                {
                    'timestamp': 1699000000000,  # Unix timestamp in ms
                    'timestamp_ms': 1699000000000,
                    'open': 35000.0,
                    'high': 35100.0,
                    'low': 34900.0,
                    'close': 35050.0,
                    'volume': 123.45,
                    'symbol': 'BTC/USD',
                    'timeframe': '1m'
                },
                ...
            ]
            ```

        Raises:
            ValueError: If symbol or timeframe is invalid
            ExchangeError: If exchange returns an error

        Example:
            ```python
            candles = await connector.fetch_ohlcv("BTC/USD", "1m", limit=100)
            latest_candle = candles[-1]
            print(f"Close: {latest_candle['close']}")
            ```
        """
        pass

    # =========================================================
    # 💰 ACCOUNT DATA
    # =========================================================

    @abstractmethod
    async def fetch_balance(self) -> Dict[str, Any]:
        """
        Fetch account balance from the exchange.

        Returns:
            Normalized balance dictionary:
            ```python
            {
                'total': {
                    'USD': 10000.0,
                    'BTC': 0.5,
                },
                'free': {
                    'USD': 8000.0,
                    'BTC': 0.3,
                },
                'used': {
                    'USD': 2000.0,
                    'BTC': 0.2,
                },
                'timestamp': 1699000000000,
                'currency': 'USD'  # Account currency
            }
            ```

        Raises:
            AuthenticationError: If API keys are invalid
            ExchangeError: If exchange returns an error

        Example:
            ```python
            balance = await connector.fetch_balance()
            free_usd = balance['free'].get('USD', 0.0)
            print(f"Available: ${free_usd}")
            ```
        """
        pass

    @abstractmethod
    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Fetch open positions from the exchange (for perpetual/futures markets).
        """
        pass

    @abstractmethod
    async def fetch_active_symbols(self) -> List[str]:
        """
        Discover all symbols that have activity (Open Positions or Open Orders).
        Used for global reconciliation and emergency sweeps.

        Returns:
            List of standard symbols (e.g., ["BTC/USDT", "ETH/USDT"])
        """
        pass

    # =========================================================
    # 📝 ORDER EXECUTION
    # =========================================================

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create an order on the exchange.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USD")
            side: Order side - 'buy' or 'sell'
            amount: Order amount in base currency
            price: Limit price (required for limit orders, ignored for market orders)
            order_type: Order type - 'market' or 'limit' (default: 'market')
            params: Additional exchange-specific parameters

        Returns:
            Normalized order result:
            ```python
            {
                'id': 'order_123456',
                'symbol': 'BTC/USD',
                'side': 'buy',
                'type': 'market',
                'status': 'closed',  # 'open', 'closed', 'canceled', 'rejected'
                'price': 35000.0,  # Execution price
                'amount': 0.1,
                'filled': 0.1,
                'remaining': 0.0,
                'cost': 3500.0,  # Total cost in quote currency
                'fee': {
                    'cost': 3.5,
                    'currency': 'USD'
                },
                'timestamp': 1699000000000,
                'trades': [...]  # List of trades (if available)
            }
            ```

        Raises:
            InsufficientFunds: If account balance is insufficient
            InvalidOrder: If order parameters are invalid
            ExchangeError: If exchange returns an error

        Example:
            ```python
            # Market order
            order = await connector.create_order(
                symbol="BTC/USD",
                side="buy",
                amount=0.1,
                order_type="market"
            )

            # Limit order
            order = await connector.create_order(
                symbol="BTC/USD",
                side="buy",
                amount=0.1,
                price=35000.0,
                order_type="limit"
            )
            ```
        """
        pass

    # =========================================================
    # 🔧 UTILITY METHODS
    # =========================================================

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize a symbol to the exchange's format.

        Different exchanges use different symbol formats:
            - Kraken: "BTC/USD" → "PF_XBTUSD"
            - Binance: "BTC/USDT" → "BTCUSDT"
            - Hyperliquid: "BTC/USD" → "BTC"

        Args:
            symbol: Standard symbol format (e.g., "BTC/USD")

        Returns:
            Exchange-specific symbol format

        Example:
            ```python
            # Kraken
            normalized = connector.normalize_symbol("BTC/USD")
            # Returns: "PF_XBTUSD"
            ```
        """
        pass

    @abstractmethod
    def denormalize_symbol(self, exchange_symbol: str) -> str:
        """
        Convert exchange-specific symbol back to standard format.

        Args:
            exchange_symbol: Exchange-specific symbol (e.g., "PF_XBTUSD")

        Returns:
            Standard symbol format (e.g., "BTC/USD")

        Example:
            ```python
            # Kraken
            standard = connector.denormalize_symbol("PF_XBTUSD")
            # Returns: "BTC/USD"
            ```
        """
        pass

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """
        Get the name of the exchange.

        Returns:
            Exchange name (e.g., "kraken", "binance", "hyperliquid")

        Example:
            ```python
            print(f"Connected to: {connector.exchange_name}")
            ```
        """
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if the connector is connected to the exchange.

        Returns:
            True if connected, False otherwise

        Example:
            ```python
            if not connector.is_connected:
                await connector.connect()
            ```
        """
        pass

    # =========================================================
    # 📊 STATUS & HEALTH (Inspirado en Hummingbot)
    # =========================================================

    @property
    def ready(self) -> bool:
        """
        Indica si el conector está listo para operar.

        Inspirado en Hummingbot's ready property.

        Un conector está "ready" cuando:
        - Está conectado al exchange
        - Ha cargado los mercados
        - Tiene balance actualizado
        - WebSocket está funcionando (si aplica)

        Returns:
            True si el conector está listo, False en caso contrario

        Example:
            ```python
            connector = KrakenConnector(...)
            await connector.connect()

            if connector.ready:
                # Safe to trade
                await connector.create_order(...)
            ```
        """
        # Default implementation: override in subclasses
        return False

    @property
    def status_dict(self) -> Dict[str, bool]:
        """
        Estado de componentes del conector.

        Inspirado en Hummingbot's status_dict property.

        Retorna un diccionario con el estado de cada componente:
        - connected: Conectado al exchange
        - markets_loaded: Mercados cargados
        - balance_updated: Balance actualizado
        - websocket_active: WebSocket funcionando (si aplica)

        Returns:
            Diccionario con estado de componentes

        Example:
            ```python
            status = connector.status_dict
            # {
            #     'connected': True,
            #     'markets_loaded': True,
            #     'balance_updated': True,
            #     'websocket_active': False
            # }
            ```
        """
        # Default implementation: override in subclasses
        return {
            "connected": False,
            "ready": self.ready,
        }

    @property
    def tracking_states(self) -> Dict[str, Any]:
        """
        Estado para persistencia.

        Inspirado en Hummingbot's tracking_states property.

        Retorna el estado interno del conector que debe ser guardado
        para recuperación después de crashes. Incluye:
        - Órdenes en tracking
        - Posiciones abiertas
        - Balance cache
        - Último timestamp procesado

        Returns:
            Diccionario con estado persistente

        Example:
            ```python
            # Guardar estado
            states = connector.tracking_states
            save_to_disk(states)

            # Recuperar estado
            states = load_from_disk()
            connector.restore_tracking_states(states)
            ```
        """
        # Default implementation: override in subclasses
        return {}

    def restore_tracking_states(self, saved_states: Dict[str, Any]):
        """
        Restaura estado guardado.

        Inspirado en Hummingbot's restore_tracking_states.

        Este método restaura el estado interno del conector desde
        un estado guardado previamente. Útil para recuperación
        después de crashes.

        Args:
            saved_states: Estado guardado previamente

        Example:
            ```python
            # Recuperar después de crash
            states = load_from_disk()
            connector.restore_tracking_states(states)
            await connector.connect()
            # Conector restaurado con estado anterior
            ```
        """
        # Default implementation: override in subclasses
        pass

    # =========================================================
    # 🔄 TRADE NORMALIZATION
    # =========================================================

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a trade from the exchange to a standard format.

        This method MUST be implemented by each connector to handle exchange-specific
        trade formats and detect if a trade is a position close with realized PnL.

        Args:
            raw_trade: Raw trade data from the exchange (CCXT format)

        Returns:
            Normalized trade dictionary with additional fields:
            ```python
            {
                **raw_trade,  # All original CCXT fields
                'is_close': bool,  # True if this trade closes a position
                'realized_pnl': float,  # Realized PnL if is_close=True
                'close_reason': str | None,  # 'TP', 'SL', 'MANUAL', or None
            }
            ```

        Implementation Guidelines:
            - Binance: Check info.positionSide and info.realizedPnl
            - Kraken: Check info.reduceOnly and info.realizedPnl
            - Bybit: Check info.reduceOnly and info.closedPnl
            - Each exchange has different fields for detecting closes

        Example (Binance):
            ```python
            def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
                info = raw_trade.get("info", {})
                realized_pnl = float(info.get("realizedPnl", 0))

                return {
                    **raw_trade,
                    'is_close': realized_pnl != 0,
                    'realized_pnl': realized_pnl,
                    'close_reason': self._detect_close_reason(info)
                }
            ```

        Example (Kraken):
            ```python
            def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
                info = raw_trade.get("info", {})

                return {
                    **raw_trade,
                    'is_close': info.get("reduceOnly", False),
                    'realized_pnl': float(info.get("realizedPnl", 0)),
                    'close_reason': self._detect_close_reason(info)
                }
            ```
        """
        # Default implementation: assume no normalization needed
        # Subclasses SHOULD override this to handle exchange-specific logic
        return {
            **raw_trade,
            "is_close": False,
            "realized_pnl": 0.0,
            "close_reason": None,
        }

    # =========================================================
    # 📈 OPTIONAL: ADVANCED FEATURES
    # =========================================================

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data for a symbol.

        This is an optional method with a default implementation that raises NotImplementedError.
        Connectors can override this if the exchange supports ticker data.

        Args:
            symbol: Trading pair symbol

        Returns:
            Ticker data dictionary

        Raises:
            NotImplementedError: If not implemented by the connector
        """
        raise NotImplementedError(f"{self.exchange_name} connector does not implement fetch_ticker")

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        Fetch order book for a symbol.

        This is an optional method with a default implementation that raises NotImplementedError.
        Connectors can override this if the exchange supports order book data.

        Args:
            symbol: Trading pair symbol
            limit: Depth of order book

        Returns:
            Order book dictionary

        Raises:
            NotImplementedError: If not implemented by the connector
        """
        raise NotImplementedError(f"{self.exchange_name} connector does not implement fetch_order_book")
