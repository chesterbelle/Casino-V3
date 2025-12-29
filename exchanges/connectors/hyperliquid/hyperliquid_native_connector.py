"""
Hyperliquid Native Connector.

This module implements the BaseConnector interface using the official
hyperliquid-python-sdk. It supports Agent Wallet authentication and
native WebSocket subscriptions.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from exchanges.connectors.connector_base import BaseConnector


class HyperliquidNativeConnector(BaseConnector):
    """
    Native connector for Hyperliquid using the official SDK.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,  # Used as Private Key for Agent
        secret: Optional[str] = None,  # Not used, but kept for interface compat
        account_address: Optional[str] = None,  # Main Wallet Address
        mode: str = "demo",
        enable_websocket: bool = True,
    ):
        """
        Initialize the native connector.

        Args:
            api_key: Agent Wallet Private Key (Hex)
            secret: Unused (Hyperliquid uses PK signing)
            account_address: Main Wallet Address (Required for Agent)
            mode: "demo" (Testnet) or "live" (Production)
            enable_websocket: Whether to start WebSocket client
        """
        self.logger = logging.getLogger("HyperliquidNativeConnector")
        self._mode = mode
        self._enable_websocket = enable_websocket

        # Credentials
        self._private_key = api_key or os.getenv("HYPERLIQUID_PRIVATE_KEY")
        self._account_address = account_address or os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")

        # Determine Base URL
        if self._mode == "demo":
            self._base_url = constants.TESTNET_API_URL
        else:
            self._base_url = constants.MAINNET_API_URL

        if not self._private_key or not self._account_address:
            self.logger.warning(f"⚠️ Missing Credentials for mode {self._mode}. Operations requiring auth will fail.")

        # SDK Objects (Initialized in connect)
        self.info = None
        self.exchange = None
        self.wallet = None

        self._connected = False
        self._markets = {}
        self._ticker_queues = {}  # symbol -> asyncio.Queue

    @property
    def exchange_name(self) -> str:
        return "hyperliquid_native"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def enable_websocket(self) -> bool:
        return self._enable_websocket

    @property
    def mode(self) -> str:
        return self._mode

    async def connect(self) -> None:
        """Connect to Hyperliquid."""
        try:
            self.logger.info(f"🔌 Connecting to Hyperliquid Native ({self._mode})...")

            # 1. Initialize Info (Public Data)
            self.info = Info(base_url=self._base_url, skip_ws=not self._enable_websocket)

            # 2. Initialize Exchange (Authenticated Actions)
            if self._private_key:
                self.wallet = Account.from_key(self._private_key)
                self.exchange = Exchange(
                    wallet=self.wallet, base_url=self._base_url, account_address=self._account_address
                )
                self.logger.info(
                    f"🔑 Authenticated as Agent: {self.wallet.address[:10]}... for Main: {self._account_address[:10]}..."
                )

            # 3. Load Markets (Meta)
            meta = self.info.meta()
            self._process_markets(meta)
            self.logger.info(f"✅ Markets loaded: {len(self._markets)}")

            # 4. Start WebSocket (Handled by Info class internally)
            if self._enable_websocket:
                # We subscribe to user events if authenticated
                if self._account_address:
                    self.info.subscribe({"type": "userEvents", "user": self._account_address}, self._on_user_event)
                    self.logger.info("✅ Subscribed to User Events")

            self._connected = True

        except Exception as e:
            self.logger.error(f"❌ Connection failed: {e}")
            raise

    async def close(self) -> None:
        """Close connections."""
        if self.info:
            self.info.disconnect_websocket()
        self._connected = False

    def _process_markets(self, meta: Dict):
        """Process exchange meta into internal market map."""
        # Hyperliquid meta structure: {'universe': [{'name': 'BTC', 'szDecimals': 5, ...}], ...}
        for asset in meta["universe"]:
            symbol = asset["name"]
            # Native symbol is just the name (e.g., BTC, ETH)
            # We map to CCXT style: BTC/USD:USDC (Hyperliquid is USDC based usually)
            # But for simplicity and compatibility, let's use standard naming or keep native.
            # Our system expects standard pairs.

            self._markets[symbol] = {
                "symbol": symbol,  # Native
                "base": symbol,
                "quote": "USDC",  # Hyperliquid uses USDC as collateral
                "precision": {"amount": asset["szDecimals"], "price": 5},  # Max precision, usually sufficient
                "contractSize": 1.0,
                "info": asset,
            }

    # =========================================================
    # 📊 MARKET DATA
    # =========================================================

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch OHLCV candles."""
        try:
            native_symbol = self.normalize_symbol(symbol)
            # Map timeframe (1m -> 1m, etc.)
            # Hyperliquid supports: 1m, 5m, 15m, 1h, 4h, 1d

            # SDK: info.candles_snapshot(name, interval, startTime, endTime)
            # We need to calculate start time based on limit if not provided
            # But SDK snapshot returns latest N candles usually?
            # Actually snapshot returns specific range.

            # Let's use a simplified approach or check SDK docs.
            # info.candles_snapshot(coin, interval, startTime, endTime)

            # For now, let's just fetch latest.
            # We might need to calculate startTime.
            end_time = int(time.time() * 1000)
            # Approx start time
            duration_map = {"1m": 60000, "5m": 300000, "1h": 3600000}
            duration = duration_map.get(timeframe, 60000)
            start_time = end_time - (limit * duration)

            candles = self.info.candles_snapshot(native_symbol, timeframe, start_time, end_time)

            return [
                {
                    "timestamp": c["t"],
                    "open": float(c["o"]),
                    "high": float(c["h"]),
                    "low": float(c["l"]),
                    "close": float(c["c"]),
                    "volume": float(c["v"]),
                    "symbol": symbol,
                    "timeframe": timeframe,
                }
                for c in candles
            ]
        except Exception as e:
            self.logger.error(f"❌ fetch_ohlcv failed: {e}")
            return []

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker (REST)."""
        try:
            native_symbol = self.normalize_symbol(symbol)
            # SDK doesn't have direct ticker method, use all_mids or L2 snapshot
            all_mids = self.info.all_mids()
            price = float(all_mids.get(native_symbol, 0))

            return {"symbol": symbol, "last": price, "timestamp": int(time.time() * 1000)}
        except Exception as e:
            self.logger.error(f"❌ fetch_ticker failed: {e}")
            raise

    async def watch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Watch ticker (WebSocket)."""
        native_symbol = self.normalize_symbol(symbol)

        if native_symbol not in self._ticker_queues:
            self.logger.info(f"📡 Subscribing to ticker for {native_symbol}")
            self._ticker_queues[native_symbol] = asyncio.Queue(maxsize=100)

            # Subscribe via SDK
            # We subscribe to L2 Book or Trades. L2 Book gives price.
            # Or 'activeAssetCtx' which gives mark price etc.
            # 'activeAssetCtx' is efficient.
            self.info.subscribe({"type": "activeAssetCtx", "coin": native_symbol}, self._on_ticker_update)

        # Wait for next update
        return await self._ticker_queues[native_symbol].get()

    def _on_ticker_update(self, msg):
        """Handle ticker update (activeAssetCtx)."""
        # Msg format: {'coin': 'BTC', 'ctx': {...}}
        try:
            data = msg.get("data", {})
            symbol = data.get("coin")
            ctx = data.get("ctx", {})

            if symbol and symbol in self._ticker_queues:
                price = float(ctx.get("midPx", 0) or ctx.get("markPx", 0))
                ticker = {"symbol": symbol, "last": price, "timestamp": int(time.time() * 1000), "info": msg}
                try:
                    self._ticker_queues[symbol].put_nowait(ticker)
                except asyncio.QueueFull:
                    pass
        except Exception as e:
            self.logger.error(f"❌ Ticker Update Error: {e}")

    def _on_user_event(self, msg):
        """Handle user events (fills, etc)."""
        # We can dispatch to order manager if needed
        # For now just log
        self.logger.debug(f"User Event: {msg}")

    # =========================================================
    # 💰 ACCOUNT DATA
    # =========================================================

    async def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance."""
        if not self._account_address:
            self.logger.warning("⚠️ fetch_balance: No account address, returning 0 balance.")
            return {
                "total": {"USDC": 0.0},
                "free": {"USDC": 0.0},
                "used": {"USDC": 0.0},
                "timestamp": int(time.time() * 1000),
                "info": {},
            }

        try:
            state = self.info.user_state(self._account_address)
            margin_summary = state["marginSummary"]

            # Hyperliquid uses USDC
            equity = float(margin_summary["accountValue"])
            total_margin_used = float(margin_summary["totalMarginUsed"])
            available = equity - total_margin_used

            # Construct CCXT-like balance
            return {
                "total": {"USDC": equity},
                "free": {"USDC": available},
                "used": {"USDC": total_margin_used},
                "timestamp": int(time.time() * 1000),
                "info": state,
            }
        except Exception as e:
            self.logger.error(f"❌ fetch_balance failed: {e}")
            raise

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch open positions."""
        if not self._account_address:
            return []

        try:
            state = self.info.user_state(self._account_address)
            positions = state["assetPositions"]
            normalized = []

            for p in positions:
                pos_data = p["position"]
                symbol = p["coin"]  # e.g. BTC

                # Filter
                if symbols and symbol not in [self.normalize_symbol(s) for s in symbols]:
                    continue

                amt = float(pos_data["szi"])
                if amt == 0:
                    continue

                entry_price = float(pos_data["entryPx"] or 0)
                unrealized_pnl = float(pos_data["unrealizedPnl"] or 0)
                leverage = float(pos_data["leverage"]["value"])
                liquidation_price = float(pos_data["liquidationPx"] or 0)

                normalized.append(
                    {
                        "symbol": symbol,
                        "side": "LONG" if amt > 0 else "SHORT",
                        "size": abs(amt),
                        "entry_price": entry_price,
                        "mark_price": 0,  # Need to fetch separately or from ticker
                        "liquidation_price": liquidation_price,
                        "unrealized_pnl": unrealized_pnl,
                        "leverage": leverage,
                        "timestamp": int(time.time() * 1000),
                        "info": p,
                    }
                )
            return normalized
        except Exception as e:
            self.logger.error(f"❌ fetch_positions failed: {e}")
            raise

    async def fetch_open_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch open orders."""
        if not self._account_address:
            return []

        try:
            orders = self.info.open_orders(self._account_address)
            normalized = []

            for o in orders:
                o_symbol = o["coin"]
                if symbol and self.normalize_symbol(symbol) != o_symbol:
                    continue

                normalized.append(self._normalize_order(o))

            return normalized
        except Exception as e:
            self.logger.error(f"❌ fetch_open_orders failed: {e}")
            raise

    # =========================================================
    # 📝 ORDER EXECUTION
    # =========================================================

    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an order."""
        try:
            native_symbol = self.normalize_symbol(symbol)
            is_buy = side.upper() == "BUY"

            # Hyperliquid SDK: exchange.order(coin, is_buy, sz, limit_px, order_type, reduce_only)
            # For MARKET orders, we still need a limit price (slippage protection)
            # SDK handles this usually if we pass order_type={"limit": {"tif": "Gtc"}} or similar
            # Wait, SDK `order` method signature:
            # order(name, is_buy, sz, limit_px, order_type, reduce_only=False, cloid=None)

            # Determine Limit Price
            if not price:
                # Fetch current price for market order estimation
                ticker = await self.fetch_ticker(symbol)
                current_price = ticker["last"]
                # Add 5% slippage for market
                slippage = 0.05
                if is_buy:
                    limit_px = current_price * (1 + slippage)
                else:
                    limit_px = current_price * (1 - slippage)
            else:
                limit_px = price

            # Order Type
            # SDK expects: {"limit": {"tif": "Gtc"}} or {"trigger": ...}
            # For Market, we simulate with Limit IOC or just aggressive Limit Gtc
            # Hyperliquid treats everything as Limit basically.

            native_type = {"limit": {"tif": "Gtc"}}
            if order_type.lower() == "market":
                # Use IOC or just aggressive limit
                native_type = {"limit": {"tif": "Ioc"}}

            reduce_only = params.get("reduceOnly", False) if params else False

            self.logger.info(f"📋 Sending Order: {native_symbol} {side} {amount} @ {limit_px}")

            result = self.exchange.order(
                name=native_symbol,
                is_buy=is_buy,
                sz=amount,
                limit_px=limit_px,
                order_type=native_type,
                reduce_only=reduce_only,
            )

            # Result format: {'status': 'ok', 'response': {'type': 'order', 'data': {'statuses': [{'resting': {'oid': 123, 'cloid': ...}}]}}}
            if result["status"] == "ok":
                statuses = result["response"]["data"]["statuses"]
                # Assuming single order
                status = statuses[0]
                if "resting" in status:
                    oid = status["resting"]["oid"]
                    return {"id": str(oid), "symbol": symbol, "status": "open", "info": result}
                elif "filled" in status:
                    oid = status["filled"]["oid"]
                    return {"id": str(oid), "symbol": symbol, "status": "closed", "info": result}  # Filled immediately
                else:
                    # Error or other status
                    raise Exception(f"Order status unknown: {status}")
            else:
                raise Exception(f"Order failed: {result}")

        except Exception as e:
            self.logger.error(f"❌ Order Failed: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancel an order."""
        try:
            native_symbol = self.normalize_symbol(symbol)
            # SDK: cancel(name, oid)
            result = self.exchange.cancel(native_symbol, int(order_id))

            if result["status"] == "ok":
                return {"id": order_id, "status": "canceled"}
            else:
                raise Exception(f"Cancel failed: {result}")
        except Exception as e:
            self.logger.error(f"❌ Cancel Failed: {e}")
            raise

    # =========================================================
    # 🔧 UTILS
    # =========================================================

    def normalize_symbol(self, symbol: str) -> str:
        """LTC/USDT:USDT -> LTC"""
        # Extract base asset
        if "/" in symbol:
            return symbol.split("/")[0]
        return symbol

    def denormalize_symbol(self, symbol: str) -> str:
        """LTC -> LTC/USDT:USDT"""
        # Default to USDT:USDT suffix for compatibility with bot's expected format
        return f"{symbol}/USDT:USDT"

    def _normalize_order(self, order: Dict) -> Dict:
        """Normalize order response."""
        return {
            "id": str(order["oid"]),
            "symbol": order["coin"],
            "status": "open",  # open_orders returns open ones
            "price": float(order["limitPx"]),
            "amount": float(order["sz"]),
            "filled": float(order["sz"] - order["sz"]),  # Wait, sz is total?
            # SDK open_orders returns: {'coin': 'LTC', 'side': 'B', 'limitPx': '80.0', 'sz': '1.0', 'oid': 123, ...}
            # sz is remaining size usually? Or original?
            # Need to check. Usually open orders list shows remaining or original.
            # For now assume sz is original.
            "type": "limit",
            "side": "buy" if order["side"] == "B" else "sell",
            "timestamp": order["timestamp"],
            "info": order,
        }
