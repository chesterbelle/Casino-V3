"""
OrderExecutor - Handles individual order execution with retry logic.

This component is responsible for:
- Executing market, limit, and stop orders
- Integrating with ErrorHandler for intelligent retry
- Validating order parameters
- Converting order results to standardized format

Author: Casino V3 Team
Version: 3.0.0
"""

import logging
from typing import Any, Dict, Optional

from core.error_handling import RetryConfig, get_error_handler


class OrderExecutor:
    """
    Executes individual orders with retry and error handling.

    Delegates actual execution to ExchangeAdapter but adds:
    - Intelligent retry logic via ErrorHandler
    - Order validation
    - Standardized error handling

    Example:
        executor = OrderExecutor(exchange_adapter)

        result = await executor.execute_market_order({
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "amount": 0.01
        })
    """

    def __init__(self, exchange_adapter, error_handler=None):
        """
        Initialize OrderExecutor.

        Args:
            exchange_adapter: ExchangeAdapter instance for order execution
            error_handler: Optional ErrorHandler (uses global if None)
        """
        self.adapter = exchange_adapter
        self.error_handler = error_handler or get_error_handler()
        self.logger = logging.getLogger("OrderExecutor")

    def _ensure_client_order_id(self, order: Dict[str, Any], prefix: str = "ENTRY") -> None:
        """
        Ensure order has a semantic clientOrderId.

        Format: C3_{PREFIX}_{uuid_short}
        e.g., C3_TP_a1b2c3d4
        """
        if "params" not in order:
            order["params"] = {}

        # If clientOrderId already exists (e.g. passed from OCOManager), don't overwrite
        if "clientOrderId" in order["params"]:
            return

        import uuid

        uid = uuid.uuid4().hex[:12]
        client_id = f"C3_{prefix}_{uid}"

        order["params"]["clientOrderId"] = client_id
        # Also set top-level for some adapters/ccxt versions
        order["clientOrderId"] = client_id

    async def execute_market_order(
        self,
        order: Dict[str, Any],
        retry_config: Optional[RetryConfig] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Execute market order with retry logic.

        Args:
            order: Order dict with symbol, side, amount
            retry_config: Optional retry configuration
            timeout: Optional operation timeout (seconds)

        Returns:
            Order result dict with order_id, status, filled_price, etc.

        Raises:
            ValidationError: If order validation fails
            ExchangeError: If order execution fails after retries
        """
        # Validate order
        self._validate_market_order(order)

        # Ensure Semantic ID (Default to ENTRY for market orders)
        self._ensure_client_order_id(order, prefix="ENTRY")

        # Execute with retry
        retry_cfg = retry_config or RetryConfig(max_retries=3, backoff_base=1.0, backoff_factor=2.0, jitter=True)

        self.logger.info(
            f"📤 Executing market order: {order['side']} {order['amount']} {order['symbol']} | ID: {order.get('clientOrderId')}"
        )

        result = await self.error_handler.execute_with_breaker(
            "exchange_orders",
            self.adapter.execute_order,
            order,
            retry_config=retry_cfg,
            timeout=timeout,
        )

        self.logger.info(f"✅ Market order executed: {result.get('order_id')} | " f"Status: {result.get('status')}")

        return result

    async def execute_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: Dict = None
    ) -> Dict[str, Any]:
        """

        Execute a limit order with retry logic.
        """
        # Round amount and price to exchange precision
        amount = float(self.adapter.amount_to_precision(symbol, amount))
        price = float(self.adapter.price_to_precision(symbol, price))

        # Validate
        order = {
            "symbol": symbol,
            "side": side,
            "type": "limit",
            "amount": amount,
            "price": price,
            "params": params or {},
        }
        self._validate_limit_order(order)

        # Ensure Semantic ID if not present (Prefix handled by caller or defaults to LIMIT)
        # Check if caller passed a specific prefix in params (e.g. from OCOManager)
        prefix = "LIMIT"
        if params and "clientOrderId_prefix" in params:
            prefix = params.pop("clientOrderId_prefix")

        self._ensure_client_order_id(order, prefix=prefix)

        retry_cfg = self._get_retry_config("limit")

        self.logger.info(
            f"📤 Executing limit order: {side} {amount} {symbol} @ {price} | ID: {order.get('clientOrderId')}"
        )

        try:
            result = await self.error_handler.execute_with_breaker(
                "exchange_orders", self.adapter.execute_order, order, retry_config=retry_cfg
            )
            self._log_execution(result, "Limit")
            return result
        except Exception as e:
            self.logger.error(f"❌ Limit order failed: {e}")
            raise

    async def execute_stop_order(
        self, symbol: str, side: str, amount: float, stop_price: float, params: Dict = None
    ) -> Dict[str, Any]:
        """
        Execute a stop order (Stop Loss) with retry logic.
        """
        # Round amount and price to exchange precision
        amount = float(self.adapter.amount_to_precision(symbol, amount))
        stop_price = float(self.adapter.price_to_precision(symbol, stop_price))

        # Prepare params with stopPrice (Binance requirement)
        order_params = params or {}
        order_params["stopPrice"] = stop_price

        order_params["reduceOnly"] = True

        # Standard STOP_MARKET logic (Old Way)
        # We allow explicit workingType if needed, but default to API default
        # order_params["workingType"] = "CONTRACT_PRICE"

        # Validate
        order = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",  # Reverted to STOP_MARKET
            "amount": amount,
            "stop_price": stop_price,
            "params": order_params,
        }
        self._validate_stop_order(order)

        # Ensure Semantic ID if not present
        prefix = "STOP"
        if params and "clientOrderId_prefix" in params:
            prefix = order_params.pop("clientOrderId_prefix")

        self._ensure_client_order_id(order, prefix=prefix)

        retry_cfg = self._get_retry_config("stop")

        self.logger.info(
            f"📤 Executing stop order: {side} {amount} {symbol} @ stop {stop_price} | ID: {order.get('clientOrderId')}"
        )

        result = await self.error_handler.execute_with_breaker(
            "exchange_orders", self.adapter.execute_order, order, retry_config=retry_cfg
        )

        self.logger.info(f"✅ Stop order executed: {result.get('order_id')}")

        return result

    def _validate_market_order(self, order: Dict[str, Any]) -> None:
        """
        Validate market order parameters.

        Args:
            order: Order dict

        Raises:
            ValueError: If validation fails
        """
        required_fields = ["symbol", "side", "amount"]
        for field in required_fields:
            if field not in order:
                raise ValueError(f"Missing required field: {field}")

        if order["amount"] <= 0:
            # EXCEPTION: Allow 0 amount if closePosition=True (Binance API requirement)
            params = order.get("params", {})
            if str(params.get("closePosition", "")).lower() == "true" or params.get("closePosition") is True:
                pass  # Valid for closePosition orders
            else:
                raise ValueError(f"Invalid amount: {order['amount']}")

        if order["side"] not in ["buy", "sell"]:
            raise ValueError(f"Invalid side: {order['side']}")

    def _validate_limit_order(self, order: Dict[str, Any]) -> None:
        """Validate limit order parameters."""
        self._validate_market_order(order)

        if "price" not in order:
            raise ValueError("Missing required field: price")

        if order["price"] <= 0:
            raise ValueError(f"Invalid price: {order['price']}")

    def _validate_stop_order(self, order: Dict[str, Any]) -> None:
        """Validate stop order parameters."""
        self._validate_market_order(order)

        # Check params for stopPrice (Binance)
        params = order.get("params", {})
        if "stopPrice" not in params:
            # Also check stop_price in top level as fallback
            if "stop_price" not in order:
                raise ValueError("Missing required field: stopPrice")

        stop_price = params.get("stopPrice") or order.get("stop_price")
        if stop_price <= 0:
            raise ValueError(f"Invalid stopPrice: {stop_price}")

    def _get_retry_config(self, order_type: str) -> RetryConfig:
        """Get retry configuration based on order type."""
        # More aggressive retries for market orders, conservative for limit/stop
        if order_type == "market":
            return RetryConfig(max_retries=3, backoff_base=1.0, backoff_factor=2.0, jitter=True)
        else:
            return RetryConfig(max_retries=3, backoff_base=1.0, backoff_factor=2.0, jitter=True)

    def _log_execution(self, result: Dict[str, Any], order_type: str) -> None:
        """Log successful execution."""
        self.logger.info(f"✅ {order_type} order executed: {result.get('order_id')} | Status: {result.get('status')}")
