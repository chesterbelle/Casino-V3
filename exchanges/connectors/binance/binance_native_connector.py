"""
Binance Native Connector - 100% Pure Implementation.

This module implements the BaseConnector interface using pure asyncio and aiohttp.
NO SDK DEPENDENCIES - all REST API calls use native HTTP with HMAC-SHA256 signing.

Architecture:
    - HTTP Client: aiohttp.ClientSession with HMAC signing
    - WebSocket: websockets library for streams
    - Rate Limiting: BinanceRateLimiter integration
"""

import asyncio
import decimal
import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
import websockets

from exchanges.connectors.connector_base import BaseConnector
from exchanges.rate_limiter import BinanceRateLimiter


class BinanceNativeConnector(BaseConnector):
    """
    Native connector for Binance Futures using pure asyncio.
    Zero SDK dependencies - all REST calls use aiohttp + HMAC signing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        mode: str = "demo",
        enable_websocket: bool = True,
    ):
        self.logger = logging.getLogger("BinanceNative")
        self._mode = mode
        self._enable_websocket = enable_websocket
        self._connected = False

        # Architecture: Error Handling
        # Import locally to avoid circular dependency
        from core.error_handling.error_handler import get_error_handler

        self.error_handler = get_error_handler()
        self._market_breaker_name = "binance_market_stream"
        self._user_breaker_name = "binance_user_stream"

        # Phase 24: Global Circuit Breaker name for REST Market Data (Pressure Relief)
        self._market_data_breaker_name = "rest_market_data"

        # API Configuration
        if mode == "demo":
            self._base_url = "https://testnet.binancefuture.com"
            self._ws_base_url = "wss://stream.binancefuture.com/ws"
            self._api_key = api_key or os.getenv("BINANCE_TESTNET_API_KEY")
            self._secret = secret or os.getenv("BINANCE_TESTNET_SECRET")
        else:
            self._base_url = "https://fapi.binance.com"
            self._ws_base_url = "wss://fstream.binance.com/ws"
            self._api_key = api_key or os.getenv("BINANCE_API_KEY")
            self._secret = secret or os.getenv("BINANCE_API_SECRET")

        # HTTP Session (created on connect)
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._time_offset = 0

        # Rate Limiter
        self._rate_limiter = BinanceRateLimiter()

        # Market Data Cache
        self._markets: Dict[str, Dict] = {}
        self._tickers: Dict[str, Dict] = {}

        # Trade Queues for blocking watch_trades
        # Key: symbol, Value: asyncio.Queue containing trade dicts
        self._trade_queues: Dict[str, asyncio.Queue] = defaultdict(lambda: asyncio.Queue(maxsize=100))

        # Ticker Queues for blocking watch_ticker
        self._ticker_queues: Dict[str, asyncio.Queue] = defaultdict(lambda: asyncio.Queue(maxsize=10))

        # WebSocket State
        self._market_data_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._market_data_task: Optional[asyncio.Task] = None
        self._active_subscriptions = set()

        # Batch & Throttle System (Phase 11)
        self._subscription_queue = asyncio.Queue()
        self._subscription_worker_task: Optional[asyncio.Task] = None
        self._subscription_batch_size = 20  # Smoother bursts (was 50)
        self._subscription_throttle_sec = 0.5  # Higher safety (was 0.33)

        # User Data Stream
        self._listen_key: Optional[str] = None
        self._user_data_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._user_data_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._order_update_callback = None

        # WS Health Tracking
        self._last_market_message_time = time.time()
        self._last_user_message_time = time.time()
        self._last_tickers_refresh = 0  # Timestamp for REST ticker cache
        self._ticker_lock = asyncio.Lock()  # Prevent Thundering Herd

        # Phase 24: Global Circuit Breaker name for REST Market Data (Pressure Relief)
        self._market_data_breaker_name = "rest_market_data"

        # Recovery State
        self._consecutive_restart_failures = 0
        self._max_simple_restarts = 3

        if not self._api_key or not self._secret:
            self.logger.warning(f"⚠️ Missing API Keys for mode {self._mode}. Operations requiring auth will fail.")

    # =========================================================
    # ABSTRACT METHOD IMPLEMENTATIONS (Required by BaseConnector)
    # =========================================================

    @property
    def exchange_name(self) -> str:
        """Return exchange name."""
        return "binance"

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected

    @property
    def enable_websocket(self) -> bool:
        """Return if WebSocket is enabled."""
        return self._enable_websocket

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to exchange format."""
        return self._normalize_symbol(symbol)

    # =========================================================
    # HTTP CLIENT - Core Native Implementation
    # =========================================================

    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds with server offset."""
        return int(time.time() * 1000) + self._time_offset

    def _sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sign parameters with HMAC-SHA256."""
        query_string = urlencode(params)
        signature = hmac.new(self._secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
        params["signature"] = signature
        return params

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        signed: bool = False,
        endpoint_type: str = "default",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Binance API with automatic retries.

        Uses the centralized ErrorHandler for exponential backoff and
        resilience on retriable errors (rate limits, server errors).
        """
        if not self._http_session:
            raise RuntimeError("HTTP session not initialized. Call connect() first.")

        url = f"{self._base_url}{endpoint}"
        params = params or {}

        if signed:
            params["timestamp"] = self._get_timestamp()
            params = self._sign_params(params)

        headers = {"X-MBX-APIKEY": self._api_key} if self._api_key else {}

        # Use ErrorHandler to execute the request with retries
        return await self.error_handler.execute(
            self._execute_raw_request,
            method,
            url,
            params,
            headers,
            endpoint_type,
            timeout=timeout,
            context=f"binance.{endpoint}",
        )

    async def _execute_raw_request(
        self,
        method: str,
        url: str,
        params: Dict[str, Any],
        headers: Dict[str, Any],
        endpoint_type: str = "default",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execution of the raw HTTP request, called by ErrorHandler."""
        # Rate limiting - Use specific bucket (Phase 14) with safety timeout
        # Default to 45s which matches our long REST timeouts but prevents indefinite hang
        await self._rate_limiter.acquire(endpoint_type, timeout=45.0)

        # Use specific timeout if provided, else session default
        req_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None

        try:
            if method == "GET":
                async with self._http_session.get(url, params=params, headers=headers, timeout=req_timeout) as resp:
                    return await self._handle_response(resp)
            elif method == "POST":
                async with self._http_session.post(url, params=params, headers=headers, timeout=req_timeout) as resp:
                    return await self._handle_response(resp)
            elif method == "DELETE":
                async with self._http_session.delete(url, params=params, headers=headers, timeout=req_timeout) as resp:
                    return await self._handle_response(resp)
            elif method == "PUT":
                async with self._http_session.put(url, params=params, headers=headers, timeout=req_timeout) as resp:
                    return await self._handle_response(resp)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except aiohttp.ClientError as e:
            self.logger.error(f"❌ HTTP request failed: {e}")
            raise

    async def _handle_response(self, resp: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Handle API response and errors."""
        text = await resp.text()

        if resp.status == 200:
            return json.loads(text) if text else {}

        # Parse error response
        try:
            error_data = json.loads(text)
            code = error_data.get("code", resp.status)
            msg = error_data.get("msg", text)
        except json.JSONDecodeError:
            code = resp.status
            msg = text

        # Phase 14: Auto-Resync on Time Error (-1021)
        if str(code) == "-1021" or "-1021" in str(msg):
            self.logger.warning("⚠️ Timestamp Error detected (-1021). Triggering Auto-Resync...")
            await self._sync_time()
            # We raise the exception, and ErrorHandler (configured with RETRIABLE -1021) will retry.
            # Since we just fixed the offset, the retry should work.

        raise Exception(f"({code}) {msg}")

    # =========================================================
    # CONNECTION MANAGEMENT
    # =========================================================

    async def connect(self) -> None:
        """Connect to Binance API."""
        if self._connected:
            return

        try:
            self.logger.info(f"🔌 Connecting to Binance Native ({self._mode})...")

            # 1. Create HTTP Session with Phase 14 optimizations
            connector = aiohttp.TCPConnector(
                limit=100,  # Total concurrent connections
                limit_per_host=20,
                use_dns_cache=True,
                ttl_dns_cache=300,
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
            self._http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)

            # 2. Sync Time
            server_time = await self._request("GET", "/fapi/v1/time")
            local_time = int(time.time() * 1000)
            self._time_offset = server_time["serverTime"] - local_time
            self.logger.info(f"✅ Time Synced. Offset: {self._time_offset}ms")

            # 3. Load Markets
            exchange_info = await self._request("GET", "/fapi/v1/exchangeInfo", endpoint_type="market_data")
            self._process_markets(exchange_info)
            self.logger.info(f"✅ Markets loaded: {len(self._markets)}")

            # 4. Check Position Mode (One-Way)
            try:
                position_mode = await self._request(
                    "GET", "/fapi/v1/positionSide/dual", signed=True, endpoint_type="account"
                )
                if position_mode.get("dualSidePosition"):
                    self.logger.info("⚠️ Switching to One-Way Mode...")
                    await self._request(
                        "POST",
                        "/fapi/v1/positionSide/dual",
                        {"dualSidePosition": "false"},
                        signed=True,
                        endpoint_type="account",
                    )
            except Exception as e:
                self.logger.warning(f"⚠️ Position Mode check failed: {e}")

            # 5. Start WebSocket Streams
            if self._enable_websocket:
                # 4. Start Websocket Stream (non-blocking)
                asyncio.create_task(self._start_market_data_stream())
                # Phase 11: Start Subscription Worker
                self._subscription_worker_task = asyncio.create_task(self._subscription_worker())

                self.logger.info("✅ WebSocket & Subscription Worker started")

            if self._enable_websocket and self._api_key and self._secret:
                await self._start_user_data_stream()

            self._connected = True
            self.logger.info("✅ Binance Native Connector connected (100% Native)")

        except Exception as e:
            self.logger.error(f"❌ Failed to connect: {e}")
            self._connected = False
            if self._http_session:
                await self._http_session.close()
                self._http_session = None
            raise

    async def _sync_time(self) -> None:
        """
        Force re-synchronization of local time with Binance server time.
        Used when -1021 (Timestamp outside recvWindow) is detected.
        """
        try:
            self.logger.warning("🕒 Syncing time with Binance...")
            # Use raw request to avoid recursion loop if this fails
            url = f"{self._base_url}/fapi/v1/time"
            if self._http_session:
                async with self._http_session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        server_time = data["serverTime"]
                        local_time = int(time.time() * 1000)
                        old_offset = self._time_offset
                        self._time_offset = server_time - local_time
                        self.logger.info(f"✅ Time Resynced. Offset: {old_offset}ms -> {self._time_offset}ms")
                    else:
                        self.logger.error(f"❌ Time sync failed: status {resp.status}")
        except Exception as e:
            self.logger.error(f"❌ Time sync exception: {e}")

    async def close(self) -> None:
        """Close all connections."""
        self.logger.info("🔌 Closing Binance Native Connector...")

        # Cancel WebSocket tasks
        for task in [
            self._market_data_task,
            self._subscription_worker_task,
            self._user_data_task,
            self._keepalive_task,
        ]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close WebSocket connections
        for ws in [self._market_data_ws, self._user_data_ws]:
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass

        # Close HTTP session
        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        self._connected = False
        self._market_data_ws = None
        self._user_data_ws = None

    async def hard_reset(self) -> bool:
        """
        Emergency Panic Button: Kills everything and forces a clean reconnection.
        Used by the Watchdog when a silent stall is detected.
        """
        self.logger.critical("🚨 HARD RESET TRIGGERED - Emergency recovery in progress...")

        try:
            # 1. Force close everything
            await self.close()

            # 2. Clear queues to prevent backlog pressure
            while not self._subscription_queue.empty():
                try:
                    self._subscription_queue.get_nowait()
                    self._subscription_queue.task_done()
                except asyncio.QueueEmpty:
                    break

            # Also clear ticker/trade queues
            for q in self._trade_queues.values():
                while not q.empty():
                    q.get_nowait()
            for q in self._ticker_queues.values():
                while not q.empty():
                    q.get_nowait()

            # 3. Small cool-off
            await asyncio.sleep(2)

            # 4. Re-establish connection
            self.logger.info("🔄 Hard Reset: Re-establishing connections...")
            await self.connect()

            self.logger.info("✅ Hard Reset complete. System should pulse again.")
            return True
        except Exception as e:
            self.logger.error(f"❌ Hard Reset FAILED: {e}", exc_info=True)
            return False

    # =========================================================
    # MARKET DATA
    # =========================================================

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch OHLCV data."""
        native_symbol = self._normalize_symbol(symbol)
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        interval = interval_map.get(timeframe, timeframe)

        params = {"symbol": native_symbol, "interval": interval, "limit": limit}
        klines = await self._request("GET", "/fapi/v1/klines", params, endpoint_type="market_data")

        return [
            {
                "timestamp": k[0],
                "timestamp_ms": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "symbol": symbol,
                "timeframe": timeframe,
            }
            for k in klines
        ]

    async def fetch_tickers(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch all 24hr tickers in a single request (Bulk).
        Binance Weight: 1 (Highly efficient).
        Uses a lock to prevent multiple simultaneous bulk fetches (Phase 14).
        """
        async with self._ticker_lock:
            # Check if another task just refreshed the tickers while we were waiting for the lock
            if time.time() - self._last_tickers_refresh < 3.0:
                self.logger.debug("⚡ Tickers recently refreshed by another task, using cache.")
                return {self.denormalize_symbol(k): v for k, v in self._tickers.items()}

            self.logger.info("📊 Fetching all symbols (Bulk Tickers REST)...")

            try:
                from core.error_handling.error_handler import RetryConfig

                # Use formal ErrorHandler for circuit breaker + selective filtering
                tickers_list = await self.error_handler.execute_with_breaker(
                    self._market_data_breaker_name,
                    self._request,
                    "GET",
                    "/fapi/v1/ticker/24hr",
                    endpoint_type="market_data",
                    timeout=30,
                    retry_config=RetryConfig(max_retries=1),  # Minimal retries here, let failover handle it
                )
            except Exception as e:
                breaker = self.error_handler.get_circuit_breaker(self._market_data_breaker_name)
                self.logger.error(f"🚨 Bulk Tickers REST failed: {e}. REST health: {breaker.state.value}")
                raise

            result = {}
            for t in tickers_list:
                native_symbol = t["symbol"]
                unified_symbol = self.denormalize_symbol(native_symbol)

                ticker_data = {
                    "symbol": unified_symbol,
                    "last": float(t.get("lastPrice", 0)),
                    "bid": float(t.get("bidPrice", 0)),
                    "ask": float(t.get("askPrice", 0)),
                    "high": float(t.get("highPrice", 0)),
                    "low": float(t.get("lowPrice", 0)),
                    "volume": float(t.get("volume", 0)),
                    "quote_volume": float(t.get("quoteVolume", 0)),
                    "change": float(t.get("priceChangePercent", 0)),
                    "timestamp": t.get("closeTime", int(time.time() * 1000)),
                }
                # Cache it
                self._tickers[native_symbol] = ticker_data
                result[unified_symbol] = ticker_data

            self._last_tickers_refresh = time.time()
            return result

    async def fetch_book_tickers(self) -> Dict[str, Dict[str, float]]:
        """
        Fetch all best bid/ask prices (Book Tickers) in a single request.
        Binance Weight: 2 (Single) or 5 (Bulk).
        """
        try:
            tickers_list = await self.error_handler.execute_with_breaker(
                self._market_data_breaker_name,
                self._request,
                "GET",
                "/fapi/v1/ticker/bookTicker",
                endpoint_type="market_data",
                timeout=15,
            )

            result = {}
            for t in tickers_list:
                unified_symbol = self.denormalize_symbol(t["symbol"])
                result[unified_symbol] = {
                    "bid": float(t.get("bidPrice", 0)),
                    "ask": float(t.get("askPrice", 0)),
                    "bid_qty": float(t.get("bidQty", 0)),
                    "ask_qty": float(t.get("askQty", 0)),
                }
            return result
        except Exception as e:
            self.logger.error(f"🚨 Fetch Book Tickers failed: {e}")
            raise

    async def fetch_order_book(self, symbol: str, limit: int = 50) -> Dict[str, Any]:
        """
        Fetch L2 Order Book (Depth) for a specific symbol.
        Used for Flytest 2.0 Depth Checks.

        Args:
            symbol: Unified symbol (e.g. "BTC/USDT:USDT")
            limit: Depth limit (5, 10, 20, 50, 100, 500, 1000). Default 50.

        Returns:
            Dict: standard order book {
                "symbol": symbol,
                "bids": [[price, qty], ...],
                "asks": [[price, qty], ...],
                "timestamp": ms
            }
        """
        native_symbol = self._normalize_symbol(symbol)

        # Valid limits for Binance Futures: 5, 10, 20, 50, 100, 500, 1000
        valid_limits = [5, 10, 20, 50, 100, 500, 1000]
        if limit not in valid_limits:
            # Snap to closest valid limit or default to 50
            limit = min(valid_limits, key=lambda x: abs(x - limit))

        try:
            data = await self.error_handler.execute_with_breaker(
                self._market_data_breaker_name,
                self._request,
                "GET",
                "/fapi/v1/depth",
                params={"symbol": native_symbol, "limit": limit},
                endpoint_type="market_data",
                timeout=10,
            )

            return {
                "symbol": symbol,
                "bids": [[float(b[0]), float(b[1])] for b in data.get("bids", [])],
                "asks": [[float(a[0]), float(a[1])] for a in data.get("asks", [])],
                "timestamp": data.get("T", int(time.time() * 1000)),
                "nonce": data.get("lastUpdateId", 0),
            }
        except Exception as e:
            self.logger.error(f"🚨 Fetch Order Book failed for {symbol}: {e}")
            raise

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch 24hr ticker for a specific symbol.
        Uses cache if fresh (< 5s old), otherwise triggers a bulk fetch.
        """
        native_symbol = self._normalize_symbol(symbol)

        # Use cache if it's recent (less than 5 seconds old)
        if time.time() - self._last_tickers_refresh < 5.0:
            if native_symbol in self._tickers:
                return self._tickers[native_symbol]

        # Otherwise, check if REST is in "Panic Mode"
        breaker = self.error_handler.get_circuit_breaker(
            self._market_data_breaker_name, failure_threshold=3, recovery_timeout=300
        )
        if breaker.is_open:
            if native_symbol in self._tickers:
                self.logger.debug(f"🚨 Panic Mode: REST Market Data is OPEN. Returning WS-Cached ticker for {symbol}")
                return self._tickers[native_symbol]
            else:
                self.logger.error(
                    f"🚨 Panic Mode: REST OPEN and {symbol} NOT in WS-Cache! Raising CircuitBreakerError."
                )
                # Raise exception to prevent OCOManager from hanging on a lock waiting for REST that will fail
                from core.error_handling.error_handler import CircuitBreakerError

                raise CircuitBreakerError(f"REST Market Data is OPEN and {symbol} not in cache")

        # Otherwise, do a bulk refresh (Weight 1) instead of individual (Weight 40)
        try:
            tickers = await self.fetch_tickers()
        except Exception:
            # If bulk refresh fails and we have it in cache, last chance fallback
            if native_symbol in self._tickers:
                self.logger.warning(f"⚠️ Bulk Tickers REST failed. Falling back to WS-Cached ticker for {symbol}")
                return self._tickers[native_symbol]
            raise
        unified_symbol = self.denormalize_symbol(native_symbol)

        if unified_symbol in tickers:
            return tickers[unified_symbol]

        # Fallback if somehow not in bulk list
        self.logger.warning(f"⚠️ {symbol} not found in bulk tickers, trying individual fetch...")
        params = {"symbol": native_symbol}
        ticker = await self._request("GET", "/fapi/v1/ticker/24hr", params, endpoint_type="market_data")
        return {
            "symbol": symbol,
            "last": float(ticker.get("lastPrice", 0)),
            "bid": float(ticker.get("bidPrice", 0)),
            "ask": float(ticker.get("askPrice", 0)),
            "high": float(ticker.get("highPrice", 0)),
            "low": float(ticker.get("lowPrice", 0)),
            "volume": float(ticker.get("volume", 0)),
            "quote_volume": float(ticker.get("quoteVolume", 0)),
            "change": float(ticker.get("priceChangePercent", 0)),
            "timestamp": ticker.get("closeTime", int(time.time() * 1000)),
        }

    # =========================================================
    # ACCOUNT DATA
    # =========================================================

    async def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance."""
        balances = await self._request("GET", "/fapi/v2/balance", signed=True, endpoint_type="account")

        result = {"total": {}, "free": {}, "used": {}}
        for b in balances:
            asset = b["asset"]
            result["total"][asset] = float(b.get("balance", 0))
            result["free"][asset] = float(b.get("availableBalance", 0))
            result["used"][asset] = result["total"][asset] - result["free"][asset]

        return result

    async def fetch_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all positions."""
        positions = await self._request("GET", "/fapi/v2/positionRisk", signed=True, endpoint_type="account")

        if isinstance(symbol, list):
            target_symbols = [self._normalize_symbol(s) for s in symbol]
        elif symbol:
            target_symbols = [self._normalize_symbol(symbol)]
        else:
            target_symbols = None

        return [
            {
                "symbol": self.denormalize_symbol(p["symbol"]),
                "side": "long" if float(p.get("positionAmt", 0)) > 0 else "short",
                "contracts": float(p.get("positionAmt", 0)),
                "entryPrice": float(p.get("entryPrice", 0)),
                "unrealizedPnl": float(p.get("unRealizedProfit", 0)),
                "leverage": int(p.get("leverage", 1)),
                "liquidationPrice": float(p.get("liquidationPrice", 0)),
                "marginType": p.get("marginType", "cross"),
                "info": p,
            }
            for p in positions
            if float(p.get("positionAmt", 0)) != 0 and (not target_symbols or p["symbol"] in target_symbols)
        ]

    async def fetch_active_symbols(self) -> List[str]:
        """Discover symbols with open positions or orders."""
        active_symbols = set()

        # 1. Check Positions
        try:
            positions = await self.fetch_positions()
            for pos in positions:
                if float(pos.get("contracts", 0)) != 0:
                    active_symbols.add(self.denormalize_symbol(pos["symbol"]))
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch positions in discovery: {e}")

        # 2. Check Orders
        try:
            orders = await self.fetch_open_orders(None)
            for o in orders:
                active_symbols.add(self.denormalize_symbol(o["symbol"]))
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch orders in discovery: {e}")

        return list(active_symbols)

    async def fetch_my_trades(self, symbol: str, since: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch user's trades (fills) for a specific symbol."""
        native_symbol = self._normalize_symbol(symbol)
        params = {"symbol": native_symbol, "limit": limit}
        if since:
            params["startTime"] = since

        trades = await self._request("GET", "/fapi/v1/userTrades", params, signed=True, endpoint_type="account")

        return [
            {
                "id": str(t["id"]),
                "order_id": str(t["orderId"]),
                "symbol": symbol,
                "side": t["side"].lower(),
                "price": float(t["price"]),
                "amount": float(t["qty"]),
                "cost": float(t["quoteQty"]),
                "fee": {
                    "cost": float(t.get("commission", 0)),
                    "currency": t.get("commissionAsset", "USDT"),
                },
                "timestamp": t["time"],
            }
            for t in trades
        ]

    # =========================================================
    # ORDERS - Regular
    # =========================================================

    async def fetch_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch ALL open orders (regular + algo). Propagates errors on failure."""
        all_orders = []

        # 1. Regular orders
        params = {}
        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)

        # self.logger.debug(f"🔍 Fetching regular orders with params: {params}")
        orders = await self._request("GET", "/fapi/v1/openOrders", params, signed=True, endpoint_type="orders")
        all_orders.extend([self._normalize_order(o) for o in orders])

        # 2. Algo/Conditional orders
        algo_orders = await self._fetch_open_algo_orders(symbol)
        all_orders.extend(algo_orders)

        return all_orders

    async def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch a single order by ID."""
        native_symbol = self._normalize_symbol(symbol)
        params = {"symbol": native_symbol}

        if order_id.isdigit():
            params["orderId"] = int(order_id)
        else:
            params["origClientOrderId"] = order_id

        try:
            order = await self._request("GET", "/fapi/v1/order", params, signed=True, endpoint_type="orders")
            return self._normalize_order(order)
        except Exception:
            # Try as algo order
            return await self._fetch_algo_order(order_id, symbol)

    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float = None,
        order_type: str = "market",
        params: Dict = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create an order with internal synchronization for reduceOnly requests."""
        params = params or {}
        native_symbol = self._normalize_symbol(symbol)

        # Format amount and price to correct precision
        formatted_amount = self.amount_to_precision(symbol, float(amount))

        args = {
            "symbol": native_symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": formatted_amount,
        }

        if price:
            args["price"] = self.price_to_precision(symbol, float(price))

        if order_type.upper() == "LIMIT":
            args["timeInForce"] = "GTC"

        # Handle client order ID
        if params.get("client_order_id"):
            args["newClientOrderId"] = params["client_order_id"]
        elif params.get("newClientOrderId"):
            args["newClientOrderId"] = params["newClientOrderId"]

        # Handle reduceOnly
        is_reduce_only = params.get("reduceOnly") or params.get("closePosition")
        if params.get("reduceOnly"):
            args["reduceOnly"] = "true"
        if params.get("closePosition"):
            args["closePosition"] = "true"
            # CRITICAL: Only pop quantity for regular API STOP_MARKET/TAKE_PROFIT_MARKET
            # Algo API does NOT support closePosition and ALWAYS requires quantity.
            if order_type.upper() not in ["STOP", "TAKE_PROFIT"]:
                args.pop("quantity", None)
            args.pop("reduceOnly", None)

        # Route to Algo API for conditional orders (Mandatory since Dec 2024 update)
        ALGO_ORDER_TYPES = {"STOP_MARKET", "STOP", "TAKE_PROFIT_MARKET", "TAKE_PROFIT", "TRAILING_STOP_MARKET", "OCO"}
        if order_type.upper() in ALGO_ORDER_TYPES:
            if params.get("stopPrice"):
                args["stopPrice"] = params["stopPrice"]

            try:
                return await self._create_algo_order(args, timeout=timeout)
            except Exception as e:
                # Intercept -4118, -2022, and -4164 for Algo orders too
                error_msg = str(e)
                if any(code in error_msg for code in ["-4118", "-2022", "-4164"]) and is_reduce_only:
                    self.logger.warning(f"⚠️ ReduceOnly Algo Sync Lag detected ({error_msg}) for {symbol}. Syncing...")
                    if await self._wait_for_position_sync(symbol):
                        return await self._create_algo_order(args, timeout=timeout)
                raise

        # Regular order
        try:
            response = await self._request(
                "POST", "/fapi/v1/order", args, signed=True, endpoint_type="orders", timeout=timeout
            )
            return self._normalize_order(response)
        except Exception as e:
            # Handle the "Speed Paradox" errors (ReduceOnly Failed because position not propagated yet)
            error_msg = str(e)
            if any(code in error_msg for code in ["-4118", "-2022", "-4164"]) and is_reduce_only:
                self.logger.warning(
                    f"⚠️ ReduceOnly Sync Lag detected ({error_msg}) for {symbol}. Waiting for position propagation..."
                )
                if await self._wait_for_position_sync(symbol):
                    self.logger.info(f"✅ Position synced for {symbol}. Retrying order...")
                    response = await self._request(
                        "POST", "/fapi/v1/order", args, signed=True, endpoint_type="orders", timeout=timeout
                    )
                    return self._normalize_order(response)
            raise

    async def _wait_for_position_sync(self, symbol: str, timeout: float = 3.0) -> bool:
        """Poll the position endpoint until a position appears (Internal Sync)."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            positions = await self.fetch_positions(symbol)
            # Check if any position exists for this symbol that isn't zero
            has_pos = any(abs(float(p.get("contracts", 0))) > 1e-8 for p in positions if p["symbol"] == symbol)
            if has_pos:
                return True
            await asyncio.sleep(0.2)  # Poll every 200ms
        self.logger.error(f"❌ Position sync TIMEOUT for {symbol} after {timeout}s")
        return False

    async def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Create a simple market order.
        Helper for emergency cleanup and standard operations.
        """
        return await self.create_order(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type="market",
            params=params,
            timeout=timeout,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> None:
        """Cancel an order (regular or algo)."""
        native_symbol = self._normalize_symbol(symbol)

        try:
            params = {"symbol": native_symbol}
            if order_id.isdigit():
                params["orderId"] = int(order_id)
            else:
                params["origClientOrderId"] = order_id

            await self._request("DELETE", "/fapi/v1/order", params, signed=True, endpoint_type="orders")
        except Exception as e:
            # Try as algo order
            if "Unknown order" in str(e) or "-2011" in str(e):
                await self._cancel_algo_order(order_id, symbol)
            else:
                raise

    async def cancel_all_orders(self, symbol: str) -> None:
        """
        Cancel ALL open orders for a symbol (Bulk + Algos).
        Binance fapi/v1/allOpenOrders (Standard) + _cancel_algo_order (Manual loop).
        """
        native_symbol = self._normalize_symbol(symbol)
        params = {"symbol": native_symbol}

        # 1. Standard Bulk Cancel (Cancellations GTC/Limit orders)
        try:
            await self._request("DELETE", "/fapi/v1/allOpenOrders", params, signed=True, endpoint_type="orders")
        except Exception as e:
            self.logger.warning(f"⚠️ Standard bulk cancel failed for {symbol}: {e}")

        # 2. Algo Orders Manual Sweep (Cancellations StopLoss/TakeProfit orders)
        try:
            algo_orders = await self._fetch_open_algo_orders(symbol)
            if algo_orders:
                self.logger.info(f"🧹 Found {len(algo_orders)} algo orders to cancel for {symbol}")
                for order in algo_orders:
                    order_id = order.get("id")
                    if order_id:
                        try:
                            await self._cancel_algo_order(order_id, symbol)
                        except Exception as inner_e:
                            self.logger.error(f"❌ Failed to cancel algo order {order_id} for {symbol}: {inner_e}")
        except Exception as e:
            self.logger.error(f"❌ Failed to sweep algo orders for {symbol}: {e}")

    # =========================================================
    # ORDERS - Algo/Conditional
    # =========================================================

    async def _fetch_open_algo_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch open algo/conditional orders. Propagates errors."""
        params = {}
        if symbol:
            params["symbol"] = self._normalize_symbol(symbol)

        # FIX: Force max limit to avoid visibility loss (default is often 20 or 100)
        params["limit"] = 1000

        response = await self._request("GET", "/fapi/v1/openAlgoOrders", params, signed=True, endpoint_type="orders")
        # Handle both list and dict responses (API version differences)
        if isinstance(response, list):
            orders = response
        else:
            orders = response.get("orders", [])
        return [self._normalize_algo_order(o) for o in orders]

    async def _fetch_algo_order(self, algo_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch single algo order."""
        native_symbol = self._normalize_symbol(symbol)
        params = {"symbol": native_symbol}

        if algo_id.isdigit():
            params["algoId"] = int(algo_id)
        else:
            params["clientAlgoId"] = algo_id

        response = await self._request("GET", "/fapi/v1/algoOrder", params, signed=True, endpoint_type="orders")
        return self._normalize_algo_order(response)

    async def _create_algo_order(self, args: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        """Create an algo/conditional order (including Native OCO)."""
        symbol = args.get("symbol")
        algo_type = args.get("algoType", "CONDITIONAL")

        # Format params
        formatted_qty = None
        if args.get("quantity"):
            formatted_qty = self.amount_to_precision(symbol, float(args["quantity"]))

        algo_params = {
            "algoType": algo_type,
            "symbol": args["symbol"],
            "side": args["side"],
            "type": args["type"],
            "quantity": formatted_qty,
        }

        # OCO Specific Prices
        if algo_type == "OCO":
            if args.get("profitPrice") is not None:
                algo_params["profitPrice"] = self.price_to_precision(symbol, float(args["profitPrice"]))
            if args.get("lossPrice") is not None:
                algo_params["lossPrice"] = self.price_to_precision(symbol, float(args["lossPrice"]))
            if args.get("lossLimitPrice") is not None:
                algo_params["lossLimitPrice"] = self.price_to_precision(symbol, float(args["lossLimitPrice"]))
        else:
            # Standard Conditional (STOP/TAKE_PROFIT)
            if args.get("stopPrice") is not None:
                algo_params["triggerPrice"] = self.price_to_precision(symbol, float(args["stopPrice"]))

        if args.get("reduceOnly"):
            algo_params["reduceOnly"] = "true"
        if args.get("newClientOrderId"):
            algo_params["clientAlgoId"] = args["newClientOrderId"]

        algo_params = {k: v for k, v in algo_params.items() if v is not None}

        self.logger.debug(f"📋 Creating {algo_type} Algo Order: {algo_params}")
        response = await self._request(
            "POST",
            "/fapi/v1/algoOrder",
            algo_params,
            signed=True,
            endpoint_type="orders",
            timeout=timeout,
        )
        return self._normalize_algo_order_response(response, args)

    async def _cancel_algo_order(self, algo_id: str, symbol: str) -> None:
        """Cancel an algo/conditional order."""
        native_symbol = self._normalize_symbol(symbol)
        params = {"symbol": native_symbol}

        if algo_id.isdigit():
            params["algoId"] = int(algo_id)
        else:
            params["clientAlgoId"] = algo_id

        await self._request("DELETE", "/fapi/v1/algoOrder", params, signed=True, endpoint_type="orders")

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
        Amend an existing order (atomic modification).
        Uses PUT /fapi/v1/order to modify price/quantity in-place.
        Crucial for ReduceOnly orders to avoid "Exceeds Position Limit" rejection.
        """
        native_symbol = self._normalize_symbol(symbol)
        args = {"symbol": native_symbol, "side": side.upper()}
        params = params or {}

        # IDs
        if order_id.isdigit():
            args["orderId"] = int(order_id)
        else:
            args["origClientOrderId"] = order_id

        # Updates
        if quantity:
            args["quantity"] = self.amount_to_precision(symbol, quantity)
        if price:
            args["price"] = self.price_to_precision(symbol, price)

        # Merge extra params (e.g. stopPrice)
        if params:
            args.update(params)

        # Standard Amend
        try:
            self.logger.info(f"🔄 Amending Order {order_id} | Price: {price} | Params: {params}")
            response = await self._request(
                "PUT", "/fapi/v1/order", args, signed=True, endpoint_type="orders", timeout=timeout
            )
            return self._normalize_order(response)
        except Exception as e:
            # If standard amend fails, check if it's an Algo Order (different endpoint)?
            # Note: Binance Algo Orders (TP/SL) usually require DELETE+CREATE, they don't support PUT often.
            # But standard LIMIT/STOP orders do.
            self.logger.warning(f"⚠️ Amend failed for {order_id}: {e}")
            raise e

    # =========================================================
    # WEBSOCKET - Market Data
    # =========================================================

    async def _start_market_data_stream(self) -> None:
        """Start market data WebSocket stream."""
        try:
            ws_url = f"{self._ws_base_url}/stream"
            self.logger.info("🔌 Connecting to Market Data Stream...")
            self._market_data_ws = await websockets.connect(
                ws_url, open_timeout=10, close_timeout=5, ping_interval=20, ping_timeout=20
            )
            self._market_data_task = asyncio.create_task(self._listen_market_data())

            # Start Subscription Worker (Phase 11)
            self._subscription_worker_task = asyncio.create_task(self._subscription_worker())

            self.logger.info("✅ Market Data Stream connected")
            self.logger.debug("Subscription Worker Active")

            # Resubscribe if reconnecting
            if self._active_subscriptions:
                asyncio.create_task(self._resubscribe_all())

        except Exception as e:
            self.logger.error(f"❌ Market Stream connection failed: {e}")
            raise

    async def _listen_market_data(self) -> None:
        """Listen loop for market data."""
        try:
            async for message in self._market_data_ws:
                self._last_market_message_time = time.time()
                try:
                    data = json.loads(message)

                    if "result" in data and "id" in data:
                        continue

                    event_type = data.get("e")
                    if event_type == "aggTrade":
                        self._handle_trade_update(data)
                    elif event_type in ("24hrTicker", "bookTicker"):
                        self._handle_ticker_update(data)

                except Exception as e:
                    self.logger.error(f"❌ Error processing market message: {e}")

        except websockets.exceptions.ConnectionClosed as e:
            await self._handle_stream_error("market", e)
        except Exception as e:
            await self._handle_stream_error("market", e)
        finally:
            self._market_data_ws = None

    async def subscribe_trades(self, symbol: str) -> None:
        """Subscribe to trade stream for a symbol."""
        native_symbol = self._normalize_symbol(symbol).lower()
        stream = f"{native_symbol}@aggTrade"
        await self._subscribe_stream(stream)
        self._active_subscriptions.add(stream)

    async def subscribe_ticker(self, symbol: str) -> None:
        """Subscribe to ticker stream for a symbol."""
        native_symbol = self._normalize_symbol(symbol).lower()
        stream = f"{native_symbol}@ticker"
        await self._subscribe_stream(stream)
        self._active_subscriptions.add(stream)

    async def watch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Watch ticker for a symbol (Blocking)."""
        native_symbol = self._normalize_symbol(symbol)
        unified_symbol = self.denormalize_symbol(native_symbol)

        # First subscribe if not already
        if f"{native_symbol.lower()}@ticker" not in self._active_subscriptions:
            await self.subscribe_ticker(symbol)
            await asyncio.sleep(0.5)

        # Return from queue (blocking) using consistent unified_symbol key
        try:
            return await self._ticker_queues[unified_symbol].get()
        except Exception as e:
            self.logger.warning(f"⚠️ Ticker queue failed for {unified_symbol}: {e}")
            return await self.fetch_ticker(symbol)

    async def watch_trades(self, symbol: str) -> Dict[str, Any]:
        """Watch trades for a symbol (Blocking)."""
        native_symbol = self._normalize_symbol(symbol)
        unified_symbol = self.denormalize_symbol(native_symbol)

        # First subscribe if not already
        if f"{native_symbol.lower()}@aggTrade" not in self._active_subscriptions:
            await self.subscribe_trades(symbol)
            await asyncio.sleep(0.5)

        # Get from queue (blocking) using consistent unified_symbol key
        return await self._trade_queues[unified_symbol].get()

    async def _subscription_worker(self) -> None:
        """
        Background worker that batches and throttles WebSocket subscriptions.
        Prevents Error 1008 (Too many requests) by group symbols together
        and respecting message frequency limits.
        """
        self.logger.debug("👷 Subscription Worker started")
        while True:
            try:
                # Wait for at least one subscription request
                first_stream = await self._subscription_queue.get()
                streams_to_sub = [first_stream]

                # Collect more if they are available in the queue (batching)
                while not self._subscription_queue.empty() and len(streams_to_sub) < self._subscription_batch_size:
                    streams_to_sub.append(self._subscription_queue.get_nowait())

                if not self._market_data_ws:
                    self.logger.warning(f"⚠️ Market WS disconnected, re-queueing {len(streams_to_sub)} streams")
                    for s in streams_to_sub:
                        self._subscription_queue.put_nowait(s)
                    await asyncio.sleep(1)
                    continue

                # Prepare and send the batch message
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": streams_to_sub,
                    "id": int(time.time() * 1000),
                }

                self.logger.debug(f"📡 Batch subscribing to {len(streams_to_sub)} streams...")
                await self._market_data_ws.send(json.dumps(subscribe_msg))

                # Mark tasks as done
                for _ in streams_to_sub:
                    self._subscription_queue.task_done()

                # Enforce throttling (Binance Limit: 5 messages/sec)
                await asyncio.sleep(self._subscription_throttle_sec)

            except asyncio.CancelledError:
                self.logger.info("🛑 Subscription Worker stopping...")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in subscription worker: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _subscribe_stream(self, stream: str) -> None:
        """Add a WebSocket stream to the subscription queue."""
        self._subscription_queue.put_nowait(stream)

    async def _resubscribe_all(self) -> None:
        """Resubscribe to all active streams after reconnection using the throttled queue."""
        self.logger.info(f"🔄 Re-queueing {len(self._active_subscriptions)} active streams for resubscription")
        for stream in self._active_subscriptions:
            await self._subscribe_stream(stream)

    def _handle_trade_update(self, data: Dict) -> None:
        """Handle trade update from WebSocket."""
        # e: aggTrade
        # s: symbol
        # p: price
        # q: quantity (using q instead of volume)
        # T: timestamp
        # m: is_buyer_maker
        native_symbol = data.get("s", "")
        # Need to map back to unified symbol if possible, but internal queue uses user-facing symbol if we knew it.
        # However, _trade_queues usage in watch_trades uses 'symbol' (user facing).
        # We need a reverse mapping or we just use what we have.
        # The watch_trades caller passes the unified symbol (e.g. BTC/USDT).
        # But data["s"] is BTCUSDT.

        # Since we don't have a reliable reverse map here easily without iterating,
        # We will assume the queue key matches the normalized symbol if we can't find it?
        # A clearer approach: store queues by NATIVE symbol since that's what we get from WS.
        # But watch_trades receives unified symbol.

        # Let's use the unified symbol stored in the _trade_queues if we can match it.
        # If we use denormalize_symbol it might work.
        unified_symbol = self.denormalize_symbol(native_symbol)

        price = float(data.get("p", 0))
        amount = float(data.get("q", 0))  # AggTrade uses q
        side = "sell" if data.get("m", False) else "buy"  # m=True means maker (sell), m=False means taker (buy)

        trade = {
            "symbol": unified_symbol,
            "id": str(data.get("a", "")),
            "price": price,
            "amount": amount,
            "side": side,
            "timestamp": data.get("T", int(time.time() * 1000)),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(data.get("T", 0) / 1000)),
        }

        # Update ticker cache as well since it's most recent price
        self._tickers[native_symbol] = {"symbol": unified_symbol, "last": price, "timestamp": trade["timestamp"]}

        # Dispatch to queue if anyone is watching
        if unified_symbol in self._trade_queues:
            queue = self._trade_queues[unified_symbol]
            if not queue.full():
                queue.put_nowait(trade)

    def _handle_ticker_update(self, data: Dict) -> None:
        """Handle ticker update from WebSocket."""
        native_symbol = data.get("s", "")
        unified_symbol = self.denormalize_symbol(native_symbol)

        self._tickers[native_symbol] = {
            "symbol": unified_symbol,
            "last": float(data.get("c", 0)),
            "bid": float(data.get("b", 0)),
            "ask": float(data.get("a", 0)),
            "timestamp": data.get("E", int(time.time() * 1000)),
        }

        # Push to queue (non-blocking, drop oldest if full)
        try:
            q = self._ticker_queues[unified_symbol]
            if q.full():
                q.get_nowait()
            q.put_nowait(self._tickers[native_symbol])
        except Exception:
            pass

    # =========================================================
    # WEBSOCKET - User Data
    # =========================================================

    async def _create_listen_key(self) -> str:
        """Create a listen key for user data stream."""
        response = await self._request("POST", "/fapi/v1/listenKey", signed=True, endpoint_type="account")
        return response["listenKey"]

    async def _keepalive_listen_key(self) -> None:
        """Keep listen key alive."""
        await self._request("PUT", "/fapi/v1/listenKey", signed=True, endpoint_type="account")

    async def _start_user_data_stream(self) -> None:
        """Start user data WebSocket stream."""
        try:
            self._listen_key = await self._create_listen_key()
            ws_url = f"{self._ws_base_url}/{self._listen_key}"

            self.logger.info("🔌 Connecting to User Data Stream...")
            self._user_data_ws = await websockets.connect(
                ws_url, open_timeout=10, close_timeout=5, ping_interval=20, ping_timeout=20
            )
            self._user_data_task = asyncio.create_task(self._listen_user_data())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            self.logger.info("✅ User Data Stream connected")

        except Exception as e:
            self.logger.error(f"❌ User Stream failed: {e}")
            raise

    async def _listen_user_data(self) -> None:
        """Listen loop for user data."""
        try:
            async for message in self._user_data_ws:
                self._last_user_message_time = time.time()
                try:
                    data = json.loads(message)
                    event = data.get("e")

                    if event == "ORDER_TRADE_UPDATE":
                        self._handle_order_update(data)
                    elif event == "STRATEGY_UPDATE":
                        self._handle_strategy_update(data)
                    elif event == "listenKeyExpired":
                        self.logger.warning("🔑 ListenKey Expired! Reconnecting...")
                        await self._reconnect_user_data_stream()

                except Exception as e:
                    self.logger.error(f"❌ User msg error: {e}")

        except Exception as e:
            await self._handle_stream_error("user", e)
        finally:
            self._user_data_ws = None

    async def _keepalive_loop(self) -> None:
        """Keepalive loop for listen key."""
        while True:
            try:
                await asyncio.sleep(30 * 60)  # 30 minutes
                await self._keepalive_listen_key()
                self.logger.debug("🔑 Listen key refreshed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ Keepalive failed: {e}")

    async def _reconnect_user_data_stream(self) -> None:
        """Reconnect user data stream."""
        if self._user_data_ws:
            try:
                await self._user_data_ws.close()
            except Exception:
                pass
        await self._start_user_data_stream()

    def _handle_order_update(self, data: Dict) -> None:
        """Handle order update from user data stream."""
        order_data = data.get("o", {})
        order_id = str(order_data.get("i", ""))
        client_order_id = order_data.get("c", "")
        status = order_data.get("X", "")

        self.logger.debug(f"🔍 WS Event: ID={order_id} c={client_order_id} X={status}")

        if self._order_update_callback:
            normalized = {
                "id": order_id,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "symbol": order_data.get("s", ""),
                "side": order_data.get("S", "").lower(),
                "type": order_data.get("o", "").lower(),
                "status": self._normalize_order_status(status),
                "price": float(order_data.get("p", 0)),
                "amount": float(order_data.get("q", 0)),
                "filled": float(order_data.get("z", 0)),
                "average": float(order_data.get("ap", 0)),
                "timestamp": order_data.get("T", int(time.time() * 1000)),
                "fee": {
                    "cost": float(order_data.get("n", 0)),
                    "currency": order_data.get("N", "USDT"),
                },
            }
            asyncio.create_task(self._order_update_callback(normalized))

    def _handle_strategy_update(self, data: Dict) -> None:
        """Handle algo order update (STRATEGY_UPDATE)."""
        strategy_data = data.get("su", {})
        algo_id = str(strategy_data.get("si", ""))
        client_algo_id = strategy_data.get("ci", "")
        status = strategy_data.get("ss", "")

        self.logger.debug(f"🔍 Algo Event: ID={algo_id} c={client_algo_id} status={status}")

        if self._order_update_callback and status in ("EXECUTED", "CANCELLED"):
            normalized = {
                "id": client_algo_id or algo_id,
                "order_id": client_algo_id or algo_id,
                "client_order_id": client_algo_id,
                "symbol": strategy_data.get("s", ""),
                "status": "closed" if status == "EXECUTED" else "canceled",
                "is_algo": True,
            }
            asyncio.create_task(self._order_update_callback(normalized))

    def set_order_update_callback(self, callback) -> None:
        """Set callback for order updates."""
        self._order_update_callback = callback

    # =========================================================
    # HEALTH CHECK
    # =========================================================

    async def ensure_websocket(self) -> None:
        """Health check + Reconnect."""
        if not self._enable_websocket:
            return

        now = time.time()
        market_stale = now - self._last_market_message_time > 60  # 60s to allow subscription setup
        market_closed = self._market_data_ws is None
        user_closed = self._user_data_ws is None and self._api_key is not None

        if market_stale or market_closed or user_closed:
            self.logger.warning(
                f"⚠️ WS Health Check Failed | "
                f"Market (Stale: {market_stale}, Closed: {market_closed}) | "
                f"User (Closed: {user_closed}). Restarting..."
            )
            await self.close()
            await asyncio.sleep(1)
            await self.connect()

    # =========================================================
    # UTILITIES
    # =========================================================

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for Binance API (e.g., 'BTC/USDT' -> 'BTCUSDT')."""
        if not symbol:
            return symbol
        return symbol.replace("/", "").replace(":USDT", "")

    async def _handle_stream_error(self, stream_type: str, error: Exception) -> None:
        """Active recovery for stream errors (Architecture: ErrorHandler)."""
        self.logger.warning(f"⚠️ Active Recovery: {stream_type} stream failed: {error}")

        # Trigger safe reconnection
        if stream_type == "market":
            asyncio.create_task(self._reconnect_market_stream_safe())
        elif stream_type == "user":
            asyncio.create_task(self._reconnect_user_stream_safe())

    async def _reconnect_market_stream_safe(self) -> None:
        """Reconnect market stream protected by Circuit Breaker."""
        from core.error_handling.error_handler import RetryConfig

        try:
            await self.error_handler.execute_with_breaker(
                self._market_breaker_name,
                self._start_market_data_stream,
                retry_config=RetryConfig(max_retries=3, backoff_base=1.0),
            )
        except Exception as e:
            self.logger.error(f"❌ Active Recovery Failed for Market: {e}")

    async def _reconnect_user_stream_safe(self) -> None:
        """Reconnect user stream protected by Circuit Breaker."""
        from core.error_handling.error_handler import RetryConfig

        try:
            await self.error_handler.execute_with_breaker(
                self._user_breaker_name,
                self._reconnect_user_data_stream,
                retry_config=RetryConfig(max_retries=3, backoff_base=1.0),
            )
        except Exception as e:
            self.logger.error(f"❌ Active Recovery Failed for User: {e}")

    def denormalize_symbol(self, symbol: str) -> str:
        """Convert exchange symbol to standard format (e.g., 'BTCUSDT' -> 'BTC/USDT:USDT')."""
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}/USDT:USDT"
        return f"{symbol}/USDT:USDT"

    def _process_markets(self, info: Dict) -> None:
        """Process exchange info to extract market data."""
        for s in info["symbols"]:
            tick_size = 0.01
            step_size = 0.001
            min_notional = 20.0  # Testnet default, mainnet is typically 5.0
            for f in s.get("filters", []):
                if f["filterType"] == "PRICE_FILTER":
                    tick_size = float(f["tickSize"])
                elif f["filterType"] == "LOT_SIZE":
                    step_size = float(f["stepSize"])
                elif f["filterType"] == "MIN_NOTIONAL":
                    min_notional = float(f.get("notional", 20.0))

            self._markets[s["symbol"]] = {
                "symbol": s["symbol"],
                "tick_size": tick_size,
                "step_size": step_size,
                "min_notional": min_notional,
                "base": s["baseAsset"],
                "quote": s["quoteAsset"],
            }

    def get_min_notional(self, symbol: str) -> float:
        """Get minimum notional value for a symbol."""
        native_symbol = self._normalize_symbol(symbol)
        market = self._markets.get(native_symbol, {})
        # Default to 20 for testnet safety
        return market.get("min_notional", 20.0)

    def _normalize_order(self, o: Dict) -> Dict[str, Any]:
        """Normalize regular order response."""
        return {
            "id": str(o.get("orderId", "")),
            "order_id": str(o.get("orderId", "")),
            "client_order_id": o.get("clientOrderId", ""),
            "symbol": o.get("symbol", ""),
            "status": self._normalize_order_status(o.get("status", "")),
            "price": float(o.get("price", 0)),
            "stopPrice": float(o.get("stopPrice", 0)),
            "amount": float(o.get("origQty", 0)),
            "filled": float(o.get("executedQty", 0)),
            "average": float(o.get("avgPrice", 0)),
            "type": o.get("type", "").lower(),
            "side": o.get("side", "").lower(),
            "timestamp": o.get("updateTime", int(time.time() * 1000)),
            "info": o,
        }

    def _normalize_algo_order(self, o: Dict) -> Dict[str, Any]:
        """Normalize algo order from list query."""
        order_id = o.get("clientAlgoId") or str(o.get("algoId", ""))
        return {
            "id": order_id,
            "order_id": order_id,
            "algo_id": str(o.get("algoId", "")),
            "symbol": o.get("symbol", ""),
            "status": o.get("algoStatus", "").lower(),
            "price": float(o.get("triggerPrice", 0) or 0),
            "amount": float(o.get("quantity", 0) or 0),
            "filled": 0.0,
            "type": o.get("orderType", "").lower(),
            "side": o.get("side", "").lower(),
            "timestamp": o.get("createTime", 0),
            "is_algo": True,
            "info": o,
        }

    def _normalize_algo_order_response(self, response: Dict, original_args: Dict) -> Dict[str, Any]:
        """Normalize algo order creation response."""
        order_id = (
            response.get("clientAlgoId")
            or str(response.get("algoOrderId", ""))
            or str(response.get("algoId", ""))
            or f"ALGO_{int(time.time() * 1000)}"
        )
        return {
            "id": order_id,
            "order_id": order_id,
            "symbol": response.get("symbol", original_args.get("symbol")),
            "status": "open",
            "price": float(response.get("triggerPrice", original_args.get("stopPrice", 0)) or 0),
            "amount": float(response.get("quantity", original_args.get("quantity", 0)) or 0),
            "type": original_args.get("type", "").lower(),
            "side": original_args.get("side", "").lower(),
            "timestamp": int(time.time() * 1000),
            "is_algo": True,
            "info": response,
        }

    def _normalize_order_status(self, status: str) -> str:
        """Normalize order status to standard format."""
        status_map = {
            "NEW": "open",
            "PARTIALLY_FILLED": "open",
            "FILLED": "closed",
            "CANCELED": "canceled",
            "CANCELLED": "canceled",
            "EXPIRED": "expired",
            "REJECTED": "rejected",
        }
        return status_map.get(status.upper(), status.lower())

    def price_to_precision(self, symbol: str, price: float) -> str:
        """Format price to symbol precision using Decimal for absolute accuracy."""
        native_symbol = self._normalize_symbol(symbol)
        if native_symbol not in self._markets:
            return str(price)

        tick_size = decimal.Decimal(str(self._markets[native_symbol]["tick_size"]))
        d_price = decimal.Decimal(str(price))

        # Proper rounding to tick_size
        rounded = (d_price / tick_size).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP) * tick_size

        # Get precision steps from tick_size string
        tick_str = format(tick_size, "f").rstrip("0")
        precision = len(tick_str.split(".")[-1]) if "." in tick_str else 0

        return f"{rounded:.{precision}f}"

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Format amount to symbol precision using Decimal (Floor rounding)."""
        native_symbol = self._normalize_symbol(symbol)
        if native_symbol not in self._markets:
            return str(amount)

        step_size = decimal.Decimal(str(self._markets[native_symbol]["step_size"]))
        d_amount = decimal.Decimal(str(amount))

        # Floor rounding for amount is safer (prevents "amount better than precision")
        rounded = (d_amount / step_size).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_DOWN) * step_size

        # Get precision from step_size
        step_str = format(step_size, "f").rstrip("0")
        precision = len(step_str.split(".")[-1]) if "." in step_str else 0

        return f"{rounded:.{precision}f}"

    def get_cached_price(self, symbol: str) -> Optional[float]:
        """Get cached ticker price."""
        native_symbol = self._normalize_symbol(symbol)
        ticker = self._tickers.get(native_symbol)
        return ticker.get("last") if ticker else None
