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

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from core.error_handling import RetryConfig, get_error_handler
from core.exceptions import ExchangeError

from .depth_profiler import DepthProfiler


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

    def __init__(self, exchange_adapter, error_handler=None, order_tracker=None, position_tracker=None):
        """
        Initialize OrderExecutor.

        Args:
            exchange_adapter: ExchangeAdapter instance for order execution
            error_handler: Optional ErrorHandler (uses global if None)
            order_tracker: Optional OrderTracker instance (Legacy local tracking)
            position_tracker: Optional PositionTracker (Legacy V3 State / alias registration)
        """
        self.adapter = exchange_adapter
        self.error_handler = error_handler or get_error_handler()
        self.order_tracker = order_tracker
        self.position_tracker = position_tracker
        self.logger = logging.getLogger("OrderExecutor")

        # Phase 102: Execution Quality - Depth Profiling
        self.depth_profiler = DepthProfiler(exchange_adapter)
        self.max_slippage_pct = 0.005  # 0.5% default threshold
        self.fragmentation_threshold_pct = 0.002  # 0.2% start fragmenting

    def _ensure_client_order_id(self, order: Dict[str, Any], prefix: str = "ENTRY") -> None:
        """
        Ensure order has a semantic clientOrderId.

        Format: C3_{PREFIX}_{uuid_short}
        e.g., C3_TP_a1b2c3d4
        """
        if "params" not in order:
            order["params"] = {}

        # If clientOrderId already exists (e.g. passed from OCOManager), don't overwrite
        # Phase 46.1: Check both formats to prevent duplicate IDs or overwrites
        if "clientOrderId" in order["params"] or "client_order_id" in order["params"]:
            # Ensure both are set if one is
            cid = order["params"].get("clientOrderId") or order["params"].get("client_order_id")
            order["params"]["clientOrderId"] = cid
            order["params"]["client_order_id"] = cid
            return

        import uuid

        uid = uuid.uuid4().hex[:12]
        # Phase 43: Universal Funnel - Standardize prefix to CASINO_
        client_id = f"CASINO_{prefix}_{uid}"

        order["params"]["clientOrderId"] = client_id
        order["params"]["client_order_id"] = client_id
        # Also set top-level for some adapters/ccxt versions
        order["clientOrderId"] = client_id
        order["client_order_id"] = client_id

    def calculate_sizing(
        self,
        symbol: str,
        bet_size: float,
        current_equity: float,
        current_price: float,
        sl_pct: float = 0.0,
        sizing_mode: str = "FIXED_NOTIONAL",
    ) -> Tuple[float, float]:
        """
        High-Frequency Hardening: Centralized Sizing Logic.
        Calculates notional position value and contract amount with precision.
        """
        if sizing_mode == "FIXED_RISK":
            if sl_pct <= 0:
                self.logger.error(f"❌ Fixed Risk Sizing requires positive Stop Loss % (got {sl_pct})")
                raise ValueError("Fixed Risk requires positive SL%")

            risk_amount = current_equity * bet_size
            position_value = risk_amount / sl_pct
        else:
            # Default: FIXED_NOTIONAL
            position_value = current_equity * bet_size

        # Calculate raw amount
        amount_raw = position_value / current_price

        # Apply Exchange Precision
        amount = float(self.adapter.amount_to_precision(symbol, amount_raw))

        self.logger.info(f"📐 Sizing Calibrated: {symbol} -> Qty: {amount}, Notional: {position_value} USDT")
        return position_value, amount

    async def execute_market_order(
        self,
        order: Dict[str, Any],
        retry_config: Optional[RetryConfig] = None,
        timeout: Optional[float] = None,
        skip_depth_analysis: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute market order with retry logic.

        Args:
            order: Order dict with symbol, side, amount
            retry_config: Optional retry configuration
            timeout: Optional operation timeout (seconds)
            skip_depth_analysis: Skip depth profiler (Phase 236: for emergency closes)

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

        if self.adapter.is_congested:
            params = order.get("params", {})
            if not params.get("reduceOnly", False):
                # Phase 240: Fail-Soft Safe Mode
                # Allow high-conviction/low-exposure entries even in congestion
                # to prevent trade volume from dropping to zero permanently.
                open_count = len(self.position_tracker.open_positions) if self.position_tracker else 0
                if open_count >= 3:
                    self.logger.warning(
                        f"🛡️ SAFE MODE ACTIVE: Rejecting entry for {order['symbol']} "
                        f"(Exposure: {open_count} positions >= limit 3)"
                    )
                    stats = getattr(self.adapter.connector, "latency_stats", {})
                    avg_lat = (stats or {}).get("avg_latency", 0)
                    raise ExchangeError(f"Safe Mode Throttled: High Latency ({avg_lat:.2f}ms) & High exposure")
                else:
                    self.logger.info(
                        f"🛡️ SAFE MODE FAIL-SOFT: Allowing entry for {order['symbol']} " f"(Exposure: {open_count} < 3)"
                    )

        # Phase 102/230/241: Execution Quality Analysis (STRIPPED for Footprint Scalping)
        # Depth profiling is removed from the hot path to eliminate latency.
        # We assume liquid symbols or handle slippage reactively via reconciliation.

        # Log the skip
        self.logger.debug(f"⚡ Footprint Fast-Track: Skipping depth analysis for {order['symbol']}")

        # Execute with retry
        retry_cfg = retry_config or RetryConfig(max_retries=3, backoff_base=1.0, backoff_factor=2.0, jitter=True)

        symbol = order["symbol"]
        self.logger.info(
            f"[TRADE] 📤 Executing Market Order: {order['side']} {order['amount']} {symbol} | ID: {order.get('clientOrderId')}"
        )

        self.logger.debug(f"[TRACE] OrderExecutor: Starting execution with 5s timeout for {symbol}...")
        result = await asyncio.wait_for(
            self.error_handler.execute_with_breaker(
                f"exchange_orders_{symbol}",
                self.adapter.execute_order,
                order,
                retry_config=retry_cfg,
                timeout=timeout,
            ),
            timeout=5.0,  # Phase 56: Strict Execution Timeout
        )
        self.logger.debug(f"[TRACE] OrderExecutor: Execution SUCCESS for {symbol}.")

        # LOCAL TRACKING: Register in OrderTracker if available
        if self.order_tracker:
            self.order_tracker.track_local_order(result)

        # Phase 238: Native Performance Restoration (Deep Clean)
        # Removed blocking polling loop entirely. If order is 'open', the Auditor
        # or OCOManager retry logic handles it reactively.

        # ENRICHMENT: Move to background to prevent blocking the critical path
        if result.get("status") == "filled":
            self.logger.debug(f"🧵 Spawning background enrichment for {result.get('order_id')}")
            asyncio.create_task(self._safe_enrichment(result, symbol))

        self.logger.info(
            f"[TRADE] ✅ Market Order: {result.get('order_id')} | "
            f"{result.get('status')} | Fee: {(result.get('fee') or {}).get('cost', 0):.4f}"
        )

        return result

    async def _enrich_fill_details(self, result: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """
        Attempt to fetch exact fill prices and fees from exchange if missing.
        """
        order_id = result.get("order_id")
        if not order_id:
            return result

        # Check if we already have fee info
        if result.get("fee") and (result.get("fee") or {}).get("cost", 0) > 0:
            return result

        # If it's a closed/filled order, try to fetch trades to get the fee
        if result.get("status") in ["closed", "filled"]:
            try:
                self.logger.info(f"🔍 Enriching fill details for order {order_id}...")
                # We wait a tiny bit for the exchange to settle the trades
                await asyncio.sleep(0.5)

                trades = await self.adapter.fetch_my_trades(symbol, limit=10)
                order_trades = [t for t in trades if str(t.get("order_id")) == str(order_id)]

                if order_trades:
                    total_fee = sum((t.get("fee") or {}).get("cost", 0) for t in order_trades)
                    avg_price = sum(t["price"] * t["amount"] for t in order_trades) / sum(
                        t["amount"] for t in order_trades
                    )

                    result["fee"] = {
                        "cost": total_fee,
                        "currency": (order_trades[0].get("fee") or {}).get("currency", "USDT"),
                    }
                    result["average"] = avg_price
                    self.logger.info(f"✨ Enriched Order {order_id}: Fee={total_fee:.4f}, AvgPrice={avg_price:.4f}")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to enrich fill details for {order_id}: {e}")

        return result

    async def _safe_enrichment(self, result: Dict[str, Any], symbol: str):
        """
        Background wrapper for enrichment to prevent main loop hangs.
        """
        try:
            # Wait 2-3 seconds for engine to settle and trades to populate
            await asyncio.sleep(2.0)
            await asyncio.wait_for(self._enrich_fill_details(result, symbol), timeout=3.0)
        except Exception as e:
            self.logger.debug(f"ℹ️ Background enrichment skipped/failed for {result.get('order_id')}: {e}")

    async def execute_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: Dict = None
    ) -> Dict[str, Any]:
        """
        Execute a limit order with retry logic.
        """
        # Phase 102: Active Latency Telemetry - Safe Mode
        if self.adapter.is_congested:
            if not (params or {}).get("reduceOnly", False):
                self.logger.warning(f"🛡️ SAFE MODE ACTIVE: Rejecting limit entry for {symbol}")
                raise ExchangeError("Safe Mode Active: High Latency")

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
            f"[TRADE] 📤 Executing Limit Order: {side} {amount} {symbol} @ {price} | ID: {order.get('clientOrderId')}"
        )

        try:
            result = await asyncio.wait_for(
                self.error_handler.execute_with_breaker(
                    f"exchange_orders_{symbol}", self.adapter.execute_order, order, retry_config=retry_cfg
                ),
                timeout=5.0,  # Phase 56: Strict Execution Timeout
            )

            # LOCAL TRACKING: Register in OrderTracker if available
            if self.order_tracker:
                self.order_tracker.track_local_order(result)

            self._log_execution(result, "Limit")
            return result
        except Exception as e:
            self.logger.error(f"❌ Limit order failed: {e}")
            raise

    async def execute_stop_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_price: float,
        params: Dict = None,
        order_type: str = "STOP_MARKET",
    ) -> Dict[str, Any]:
        """
        Execute a stop order (Stop Loss or Take Profit) with retry logic.
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
            "type": order_type,  # Allow override (e.g. TAKE_PROFIT_MARKET)
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
            f"[OCO] 📤 Executing Stop Order: {side} {amount} {symbol} @ stop {stop_price} | ID: {order.get('clientOrderId')}"
        )

        result = await asyncio.wait_for(
            self.error_handler.execute_with_breaker(
                f"exchange_orders_{symbol}", self.adapter.execute_order, order, retry_config=retry_cfg
            ),
            timeout=5.0,  # Phase 56: Strict Execution Timeout
        )

        # LOCAL TRACKING: Register in OrderTracker if available
        if self.order_tracker:
            self.order_tracker.track_local_order(result)

        self.logger.info(f"[OCO] ✅ Stop Order Executed: {result.get('order_id')}")

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

    async def force_close_position(
        self, symbol: str, side: str, amount: float, skip_depth_analysis: bool = True
    ) -> Dict[str, Any]:
        """
        Force close a position with "Smart Close" fallback logic.

        Strategy:
        1. Market Order (Preferred)
        2. Aggressive Limit (5% buffer) - if Market blocked by volatility
        3. Safe Limit (1% buffer) - if Aggressive blocked by price bands

        Phase 236: skip_depth_analysis defaults to True for force closes.
        """
        symbol = self.adapter.normalize_symbol(symbol)
        # Invert side for closing
        # side argument is the POSITION side (LONG/SHORT)
        # close_side is the ORDER side (SELL/BUY)
        close_side = "sell" if side.upper() == "LONG" else "buy"

        self.logger.info(f"📉 Force Closing {symbol} {side} {amount} (Smart Close)")

        # Generate Universal ID
        import uuid

        client_id = f"CASINO_FC_{uuid.uuid4().hex[:12]}"

        # TIER 0: Market Close
        try:
            # Phase 78.1: Pre-Register Alias (Silent Close Fix)
            if self.position_tracker:
                positions = self.position_tracker.get_positions_by_symbol(symbol)
                for pos in positions:
                    if pos.status != "CLOSED":
                        self.position_tracker.register_alias(client_id, pos)
                        self.logger.info(f"💾 Pre-Registered Close Alias: {client_id} -> {pos.trade_id}")
                        break  # Only link to the first active position

            return await self.execute_market_order(
                {
                    "symbol": symbol,
                    "side": close_side,
                    "amount": amount,
                    "params": {"reduceOnly": True, "client_order_id": client_id},
                },
                skip_depth_analysis=skip_depth_analysis,
            )
        except Exception as e:
            err_str = str(e).lower()
            # Check for specific binance errors preventing market orders
            # -4131: PERCENT_PRICE filter (Market order price out of bounds due to volatility)
            # -2021: Order would trigger immediately (sometimes with FOK/IOC market orders)
            # -1013: Filter failure
            if "-4131" in err_str or "percent_price" in err_str or "filter" in err_str:
                self.logger.warning(f"⚠️ Market Close blocked for {symbol} ({e}). Initiating Smart Close Fallbacks...")
                return await self._execute_smart_close_fallback(symbol, close_side, amount)

            raise e

    async def _execute_smart_close_fallback(self, symbol: str, close_side: str, amount: float) -> Dict[str, Any]:
        """Tier 1 & 2 Fallback logic for closures."""
        try:
            current_price = await self.adapter.get_current_price(symbol)

            # TIER 1: Aggressive Limit (5% buffer)
            # Simulates a Market order but strictly defined to pass PERCENT_PRICE if bands are wide enough
            buffer = 0.95 if close_side == "sell" else 1.05
            limit_price = float(self.adapter.price_to_precision(symbol, current_price * buffer))

            import uuid

            client_id = f"CASINO_FC1_{uuid.uuid4().hex[:12]}"

            self.logger.info(f"🔄 Smart Close T1: Aggressive LIMIT {close_side} @ {limit_price} (5%)")

            # Phase 78.1: Pre-Register Alias for T1
            if self.position_tracker:
                positions = self.position_tracker.get_positions_by_symbol(symbol)
                for pos in positions:
                    if pos.status != "CLOSED":
                        self.position_tracker.register_alias(client_id, pos)
                        break

            return await self.execute_limit_order(
                symbol=symbol, side=close_side, amount=amount, price=limit_price, params={"client_order_id": client_id}
            )

        except Exception as tier1_e:
            err_str = str(tier1_e).lower()
            # If Aggressive Limit fails due to price band (-4016), we must respect exchange bounds
            if "-4016" in err_str or "limit price" in err_str:
                self.logger.warning("⚠️ Aggressive Limit blocked. Initiating T2 Safe Limit...")

                # TIER 2: Safe Limit (1% buffer)
                # Almost guaranteed to be inside bands, but might not fill immediately if price runs away
                buffer = 0.99 if close_side == "sell" else 1.01
                limit_price = float(self.adapter.price_to_precision(symbol, current_price * buffer))

                import uuid

                client_id = f"CASINO_FC2_{uuid.uuid4().hex[:12]}"

                self.logger.info(f"🔄 Smart Close T2: Safe LIMIT {close_side} @ {limit_price} (1%)")

                # Phase 78.1: Pre-Register Alias for T2
                if self.position_tracker:
                    positions = self.position_tracker.get_positions_by_symbol(symbol)
                    for pos in positions:
                        if pos.status != "CLOSED":
                            self.position_tracker.register_alias(client_id, pos)
                            break

                return await self.execute_limit_order(
                    symbol=symbol,
                    side=close_side,
                    amount=amount,
                    price=limit_price,
                    params={"client_order_id": client_id},
                )

            raise tier1_e

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an order with retry logic and standard logging.
        """
        try:
            self.logger.info(f"🗑️ Cancelling Order: {order_id} ({symbol})")
            await self.error_handler.execute_with_breaker(
                f"exchange_cancel_{symbol}",
                self.adapter.cancel_order,
                order_id,
                symbol,
                retry_config=self._get_retry_config("market"),  # Use aggressive retry for cancels
            )
            self.logger.info(f"✅ Order {order_id} cancelled.")
            return True
        except Exception as e:
            # Idempotency: If order doesn't exist (-2011), consider it cancelled
            if "-2011" in str(e) or "Unknown order" in str(e):
                self.logger.info(f"✅ Cancel skipped: Order {order_id} already gone.")
                return True

            self.logger.error(f"❌ Failed to cancel order {order_id}: {e}")
            raise e

    def _log_execution(self, result: Dict[str, Any], order_type: str) -> None:
        """Log successful execution."""
        self.logger.info(f"✅ {order_type} order executed: {result.get('order_id')} | Status: {result.get('status')}")

    async def _execute_fragmented_market_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 102: Fragmented Execution - Breaks large orders into chunks."""
        symbol = order["symbol"]
        # side = order["side"]
        total_amount = order["amount"]

        # Split into 3 chunks for now (Industrial Standard approach: Time-Weighted Average Price)
        # In a real HFT bot, we'd use dynamic chunk sizing, but 3 chunks is a safe baseline.
        num_chunks = 3
        chunk_amount = float(self.adapter.amount_to_precision(symbol, total_amount / num_chunks))

        if chunk_amount <= 0:
            self.logger.warning(f"⚠️ Chunk size too small for {symbol}. Executing as single order.")
            # Restore execution without fragmentation to avoid recursion
            return await self.error_handler.execute_with_breaker(
                f"exchange_orders_{symbol}", self.adapter.execute_order, order
            )

        self.logger.info(f"🧩 Fragmenting order: {total_amount} -> {num_chunks} chunks of {chunk_amount}")

        results = []
        remaining = total_amount

        for i in range(num_chunks):
            # Last chunk takes the remainder
            current_chunk = chunk_amount if i < num_chunks - 1 else remaining

            # Phase 232: Small amount safety
            if current_chunk <= 0:
                if i == num_chunks - 1 and results:
                    break  # Already done
                continue

            chunk_order = order.copy()
            # Ensure last fragment is rounded correctly to avoid precision errors
            chunk_order["amount"] = float(self.adapter.amount_to_precision(symbol, current_chunk))

            # Ensure we don't try to send 0.0 after precision rounding
            if float(chunk_order["amount"]) <= 0:
                if i == num_chunks - 1:
                    break
                continue

            self._ensure_client_order_id(chunk_order, prefix=f"FRAG_{i}")

            self.logger.info(f"📤 Executing Frag {i+1}/{num_chunks}: {chunk_order['amount']} {symbol}")
            res = await self.adapter.execute_order(chunk_order)

            # Phase 232: Market Polish for fragments
            if res.get("status") == "open":
                f_id = res.get("order_id") or res.get("id")
                for poll_i in range(3):
                    self.logger.info(f"⏳ Polling Frag {i+1} {f_id} (Attempt {poll_i+1})...")
                    await asyncio.sleep(0.5)
                    try:
                        updated = await self.adapter.fetch_order(f_id, symbol)
                        if updated.get("status") in ["closed", "filled"]:
                            res.update(updated)
                            self.logger.info(f"✅ Frag {i+1} filled after polling.")
                            break
                    except Exception:
                        pass

            results.append(res)

            # Phase 232 diagnostic: Log actual fill for this frag
            f_id = res.get("order_id") or res.get("id")
            f_filled = float(res.get("filled", 0))
            f_status = res.get("status")
            self.logger.info(f"📥 Frag {i+1}/{num_chunks} Response: ID={f_id}, Status={f_status}, Filled={f_filled}")

            # Substract what was ACTUALLY requested in formatted units
            remaining -= float(chunk_order["amount"])
            # Ensure remaining doesn't go slightly negative due to float noise
            remaining = max(0, remaining)
            # Small delay between chunks to let book recover
            if i < num_chunks - 1:
                await asyncio.sleep(0.5)

        # Aggregate results (Phase 230: Fix Result Mismatch)
        if not results:
            return {"error": "fragmentation_failed"}

        # Use the last successful result as a template but update with aggregated values
        final_result = results[-1].copy()

        # Phase 232: Strict Fill Counting (Don't fall back to 'amount'!)
        total_filled = sum(float(r.get("filled", 0)) for r in results)

        total_cost = sum(
            float(r.get("cost") or (float(r.get("filled", 0)) * float(r.get("average", 0))) or 0) for r in results
        )
        total_fee = sum(float((r.get("fee") or {}).get("cost", 0)) for r in results if r.get("fee"))

        final_result["amount"] = total_amount  # Original requested amount
        final_result["filled"] = total_filled
        final_result["cost"] = total_cost
        if total_filled > 0:
            final_result["average"] = total_cost / total_filled
            final_result["price"] = final_result["average"]

        if total_fee > 0:
            final_result["fee"] = {
                "cost": total_fee,
                "currency": (results[0].get("fee") or {}).get("currency", "USDT"),
            }

        self.logger.info(
            f"✅ Fragmented Order Aggregated: {total_amount} {symbol} | "
            f"Filled: {total_filled} | AvgPrice: {final_result.get('average', 0):.4f}"
        )

        return final_result
