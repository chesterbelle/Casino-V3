"""
OCOManager - Manages OCO (One-Cancels-Other) bracket orders.

This component is responsible for:
- Creating bracketed orders (Main + TP + SL)
- Ensuring atomicity of OCO creation
- Waiting for fill confirmation via WebSocket
- Validating OCO integrity (all 3 orders exist)
- Cleanup on partial failure

Author: Casino V3 Team
Version: 3.0.0
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

from core.error_handling import RetryConfig, get_error_handler
from core.observability.watchdog import watchdog
from core.portfolio.position_tracker import OpenPosition, PositionTracker
from utils.symbol_norm import normalize_symbol

# Timeout for price fetching during OCO (protects against REST breaker hangs)
OCO_PRICE_FETCH_TIMEOUT = 10.0  # seconds
OCO_OPERATION_TIMEOUT = 180.0  # Increased for high-volume Testnet (3 minutes)


class OCOAtomicityError(Exception):
    """Raised when OCO bracket creation fails atomically."""

    pass


class OCOManager:
    """
    Manages creation and validation of OCO bracket orders.

    OCO Flow:
    1. Execute main market order
    2. Wait for fill confirmation (WebSocket or polling)
    3. Create TP limit order
    4. Create SL stop order
    5. Validate all 3 orders exist
    6. If any step fails: cleanup and raise error

    Example:
        oco_manager = OCOManager(order_executor, position_tracker, exchange_adapter)

        result = await oco_manager.create_bracketed_order({
            "symbol": "BTC/USDT:USDT",
            "side": "LONG",
            "size": 0.01,
            "take_profit": 1.01,
            "stop_loss": 0.99
        })
    """

    def __init__(self, order_executor, position_tracker: PositionTracker, exchange_adapter):
        """
        Initialize OCOManager.

        Args:
            order_executor: OrderExecutor instance
            position_tracker: PositionTracker instance
            exchange_adapter: ExchangeAdapter for price fetching
        """
        self.executor = order_executor
        self.tracker = position_tracker
        self.adapter = exchange_adapter
        self.logger = logging.getLogger("OCOManager")
        self.error_handler = get_error_handler()

        # Retry config for TP/SL orders
        # Retry config for TP/SL orders (Backoff increased to 1.5s for -2022 ReduceOnly race condition)
        self.tpsl_retry_config = RetryConfig(max_retries=6, backoff_base=1.5, backoff_factor=2.0, jitter=True)

        # Pending fill futures: order_id -> asyncio.Future
        self.pending_orders: Dict[str, asyncio.Future] = {}

        # Pending symbols (In-flight lock)
        # Prevents double-entry during network latency
        self.pending_symbols: set[str] = set()

    async def on_order_update(self, order: Dict[str, Any]) -> None:
        """
        Handle order update event from WebSocket.
        Resolves pending future if we are waiting for this order to fill.
        """
        order_id = str(order.get("id") or order.get("order_id", ""))
        status = order.get("status", "").lower()

        if order_id in self.pending_orders:
            future = self.pending_orders[order_id]
            if not future.done():
                if status in ["filled", "closed"]:
                    # Pass full order data for Phase 30 fee capture
                    future.set_result(order)
                    self.logger.debug(f"[OCO] Resolved future for order {order_id}")
                elif status in ["canceled", "rejected", "expired"]:
                    future.set_exception(OCOAtomicityError(f"Order {order_id} failed with status: {status}"))

    async def create_bracketed_order(
        self, order: Dict[str, Any], wait_for_fill: bool = True, fill_timeout: float = 30.0, contributors: list = None
    ) -> Dict[str, Any]:
        """
        Create complete OCO bracket order with atomicity guarantees.

        Args:
            order: Order dict with:
                - symbol: Trading symbol
                - side: "LONG" or "SHORT"
                - size: Position size (fraction of equity)
                - take_profit: TP multiplier (e.g., 1.01 = +1%)
                - stop_loss: SL multiplier (e.g., 0.99 = -1%)
            wait_for_fill: Whether to wait for main order fill
            fill_timeout: Timeout for fill confirmation (seconds)

        Returns:
            Dict with:
                - main_order: Main order result
                - tp_order: Take profit order result
                - sl_order: Stop loss order result
                - fill_price: Actual fill price

        Raises:
            OCOAtomicityError: If OCO bracket creation fails
            TimeoutError: If fill confirmation times out
        """
        symbol = order["symbol"]
        side = order["side"]

        # DEBUG: OCO DATA CHECK - Critical for Notional Debugging
        amt_debug = order.get("amount", 0)
        prc_debug = order.get("price") or 0
        notional_debug = amt_debug * prc_debug if amt_debug and prc_debug else 0
        self.logger.info(
            f"🔍 OCO DATA CHECK | Symbol: {symbol} | Amount: {amt_debug} | "
            f"Price: {prc_debug} | Calc Notional: {notional_debug:.4f}"
        )

        self.logger.info(
            f"🛡️ Creating OCO bracket for {symbol} {side} | "
            f"TP: {order.get('take_profit', 0):.4f} | SL: {order.get('stop_loss', 0):.4f}"
        )

        # Validate TP/SL presence
        if "take_profit" not in order or "stop_loss" not in order:
            raise ValueError("Order must contain 'take_profit' and 'stop_loss'")
        main_order = None
        tp_order = None
        sl_order = None
        position = None

        # 0. NORMALIZE SYMBOL
        raw_symbol = order.get("symbol", "")
        symbol = normalize_symbol(raw_symbol)
        order["symbol"] = symbol  # Update in-place so downstream sees normalized symbol

        # 1. LOCK SYMBOL (Concurrency Protection)
        if symbol in self.pending_symbols:
            self.logger.warning(f"⚠️ Rejecting duplicate OCO request for {symbol} (Already pending)")
            raise OCOAtomicityError(f"Symbol {symbol} is already processing an order")

        self.pending_symbols.add(symbol)

        # WATCHDOG INTEGRATION: Register OCO operation for monitoring
        operation_id = f"oco_{symbol}_{uuid.uuid4().hex[:8]}"
        watchdog.register(operation_id, timeout=OCO_OPERATION_TIMEOUT)

        try:
            # 0. PRE-VALIDATE PRICES (Sanity Check)
            # Prevents filling entry for markets where tick_size rounds TP/SL to 0.0
            try:
                watchdog.heartbeat(operation_id, f"Fetching price for {symbol}")
                # TIMEOUT PROTECTION: Prevents hang when REST breaker is open
                est_price = await asyncio.wait_for(
                    self.adapter.get_current_price(symbol), timeout=OCO_PRICE_FETCH_TIMEOUT
                )
                watchdog.heartbeat(operation_id, f"Got price {est_price}")
                tp_est, sl_est = self._calculate_tp_sl_prices(
                    est_price, side, order["take_profit"], order["stop_loss"], symbol
                )
                if tp_est <= 0 or sl_est <= 0:
                    raise OCOAtomicityError(
                        f"Pre-validation failed: TP/SL would round to 0.0 (Price: {est_price}, tick_size check needed)"
                    )
            except asyncio.TimeoutError:
                raise OCOAtomicityError(f"Price fetch timed out for {symbol} (REST may be blocked)")
            except Exception as e:
                if isinstance(e, OCOAtomicityError):
                    raise
                self.logger.warning(f"⚠️ Pre-validation skipped (price fetch failed): {e}")

            # PRE-RESERVE CLIENT ORDER ID (To prevent race conditions with WS Fill Events)
            client_order_id = f"C3_ENTRY_{uuid.uuid4().hex[:12]}"

            # Pre-register future in pending_orders (so if event arrives before new_order returns, we catch it)
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self.pending_orders[client_order_id] = future
            # Step 1: Execute main market order
            main_order = await self._execute_main_order(order, client_order_id=client_order_id)
            watchdog.heartbeat(
                operation_id, f"Main order executed: {main_order.get('order_id') or main_order.get('id')}"
            )

            # Log the response for debugging
            self.logger.debug(f"Main order response: {main_order}")

            # Validate main_order has required fields
            if not main_order:
                raise OCOAtomicityError("Main order returned None")

            if "order_id" not in main_order and "id" not in main_order:
                self.logger.error(f"Main order missing order_id. Response: {main_order}")
                raise OCOAtomicityError(f"Main order missing order_id. Got: {list(main_order.keys())}")

            # Normalize order_id field (some exchanges use 'id' instead of 'order_id')
            order_id = main_order.get("order_id") or main_order.get("id")

            # Register numeric ID as well (pointing to same future)
            # This covers cases where WS event prioritizes numeric ID over client ID
            if order_id and order_id != client_order_id:
                self.pending_orders[str(order_id)] = future

            # Step 2: Wait for fill confirmation or use immediate response
            fill_data = None
            if wait_for_fill:
                fill_data = await self._wait_for_fill(order_id, symbol, timeout=fill_timeout, future=future)
            else:
                # For market orders, use response price immediately (faster)
                # The connector is responsible for normalizing the price (including calculating from cumQuote if needed)
                fill_price_from_response = (
                    main_order.get("price") or main_order.get("avgPrice") or main_order.get("average")
                )
                if fill_price_from_response and float(fill_price_from_response) > 0:
                    fill_data = main_order
                else:
                    # Last resort: check fills array (standard CCXT structure)
                    if main_order.get("fills") and len(main_order["fills"]) > 0 and main_order["fills"][0].get("price"):
                        fill_data = main_order

            # If we still don't have fill_data (e.g. order status is NEW), we MUST wait for fill
            if not fill_data or float(fill_data.get("price") or fill_data.get("average") or 0) <= 0:
                self.logger.info("⏳ Fill price not in response (status NEW?), waiting for fill...")
                try:
                    fill_data = await self._wait_for_fill(order_id, symbol, timeout=fill_timeout, future=future)
                except Exception as e:
                    self.logger.error(f"❌ Failed to wait for fill: {e}")
                    raise OCOAtomicityError(f"Failed to get fill price: {e}")

            # Extract precise data from fill (Phase 30)
            fill_price = float(fill_data.get("price") or fill_data.get("average") or 0)
            entry_fee = float(fill_data.get("fee", {}).get("cost", 0) or 0)

            watchdog.heartbeat(operation_id, f"Main filled at {fill_price} (Fee: {entry_fee})")
            self.logger.info(f"✅ Main order filled @ {fill_price} (Fee: {entry_fee})")

            # Step 2.5: REGISTER TENTATIVE POSITION (State Machine: OPENING)
            # This protects against "Stale Read" by Reconciliation Service during TP/SL creation.

            # Calculate TP/SL prices (needed for position object)
            tp_price, sl_price = self._calculate_tp_sl_prices(
                fill_price, side, order["take_profit"], order["stop_loss"], symbol
            )

            # CRITICAL: Final validation with ACTUAL fill price
            if tp_price <= 0 or sl_price <= 0:
                self.logger.error(f"❌ Actual fill price {fill_price} resulted in 0.0 TP/SL! Aborting.")
                raise OCOAtomicityError(f"Invalid OCO prices calculated: TP={tp_price}, SL={sl_price}")

            # Calculate liquidation level
            entry_price = fill_price
            leverage = order.get("leverage", 1)
            liquidation_level = None
            if leverage > 0:
                if side == "LONG":
                    liquidation_level = entry_price * (1.0 - (1.0 / leverage) + 0.005)
                elif side == "SHORT":
                    liquidation_level = entry_price * (1.0 + (1.0 / leverage) - 0.005)

            # Create position object with status="OPENING"
            position = OpenPosition(
                trade_id=main_order.get("order_id") or main_order.get("id"),
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                entry_timestamp=main_order.get("timestamp", ""),
                margin_used=order.get("margin_used", 0),
                notional=order.get("notional", 0),
                leverage=leverage,
                tp_level=tp_price,
                sl_level=sl_price,
                liquidation_level=liquidation_level,
                order=order,
                main_order_id=main_order.get("order_id") or main_order.get("id"),
                tp_order_id=None,  # Pending
                sl_order_id=None,  # Pending
                exchange_tp_id=None,  # Pending
                exchange_sl_id=None,  # Pending
                contributors=contributors or [],
                status="OPENING",  # CRITICAL: Signals "Construction in Progress"
            )

            # Add to tracker IMMEDIATELY
            self.tracker.open_positions.append(position)
            self.tracker.total_trades_opened += 1
            position.entry_fee = entry_fee  # Phase 30

            # Update granular counters for Session Report
            if side == "LONG":
                self.tracker.new_longs += 1
            else:
                self.tracker.new_shorts += 1

            self.tracker._trigger_state_change()
            self.logger.info(f"[TRADE] 🛡️ Position Opening: {position.trade_id} (Protection pending)")

            try:
                # =========================================================
                # HARDENED MANUAL OCO FLOW
                # =========================================================
                self.logger.info(f"[OCO] 🛡️ Creating Protected Bracket (Manual) for {symbol}")

                # Step 4: Create TP order
                tp_order = await self._create_tp_order(symbol, side, main_order["amount"], tp_price)
                watchdog.heartbeat(operation_id, f"TP order created: {tp_order.get('order_id') or tp_order.get('id')}")

                # Step 5: Create SL order
                sl_order = await self._create_sl_order(symbol, side, main_order["amount"], sl_price)
                watchdog.heartbeat(operation_id, f"SL order created: {sl_order.get('order_id') or sl_order.get('id')}")

                # Step 6: Validate OCO completeness
                self._validate_oco_complete(main_order, tp_order, sl_order)

                # Step 7: Register OCO pair
                tp_order_id = tp_order.get("order_id") or tp_order.get("id")
                sl_order_id = sl_order.get("order_id") or sl_order.get("id")
                await self.error_handler.execute_with_breaker(
                    f"oco_register_{symbol}",
                    self.adapter.register_oco_pair,
                    symbol,
                    tp_order_id,
                    sl_order_id,
                    retry_config=RetryConfig(max_retries=3, backoff_base=0.5, backoff_factor=2.0),
                )
                watchdog.heartbeat(operation_id, "OCO pair registered")

                self.logger.info(
                    f"[OCO] ✅ Bracket Active | Main: {main_order.get('order_id') or main_order.get('id')} | "
                    f"TP: {tp_order_id} | SL: {sl_order_id}"
                )

                # UPDATE POSITION STATE WITH DUAL IDs
                position.tp_order_id = tp_order.get("client_order_id") or tp_order_id
                position.exchange_tp_id = tp_order.get("order_id") or tp_order_id
                position.sl_order_id = sl_order.get("client_order_id") or sl_order_id
                position.exchange_sl_id = sl_order.get("order_id") or sl_order_id

                # Finalize position state
                position.status = "ACTIVE"
                self.tracker._trigger_state_change()
                self.logger.info(f"[TRADE] ✅ Position Active: {position.trade_id}")

            except Exception as e:
                # If TP/SL creation fails, the position is broken/partial.
                # _cleanup_partial_oco will close it on exchange.
                # We must also remove it from tracker.
                self.logger.error("❌ OCO Creation failed after Position Registration. Rolling back state...")
                await self.tracker.remove_position(position.trade_id)
                raise e

            return {
                "main_order": main_order,
                "tp_order": tp_order,
                "sl_order": sl_order,
                "fill_price": fill_price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "contributors": contributors,
                "position": position,
            }

        except Exception as e:
            # Cleanup on failure
            self.logger.error(f"❌ OCO bracket creation failed: {e!r}")
            if "main_order" in locals() and main_order:
                # Only cleanup if main_order was created
                await self._cleanup_partial_oco(
                    main_order,
                    tp_order if "tp_order" in locals() else None,
                    sl_order if "sl_order" in locals() else None,
                )
            if position:
                await self.tracker.remove_position(position.trade_id)
            raise OCOAtomicityError(f"Failed to create OCO bracket: {e}") from e

        finally:
            # UNLOCK SYMBOL
            if symbol in self.pending_symbols:
                self.pending_symbols.remove(symbol)
            # WATCHDOG CLEANUP: Unregister operation monitoring
            try:
                watchdog.unregister(operation_id)
            except Exception:
                pass  # Ignore errors during cleanup

    async def modify_bracket(
        self,
        trade_id: str,
        symbol: str,
        new_tp_price: Optional[float] = None,
        new_sl_price: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Modifies an existing bracket (Native or Manual).
        If Native OCO: cancels the current OCO and creates a new one.
        If Manual OCO: replaces only the necessary leg.
        """
        position = self.tracker.get_position(trade_id)
        if not position:
            raise ValueError(f"Position not found: {trade_id}")

        # Determine if it's a native bracket
        is_native = (
            position.exchange_tp_id is not None
            and position.exchange_sl_id is not None
            and position.exchange_tp_id == position.exchange_sl_id
        )

        tp_price = new_tp_price or position.tp_level
        sl_price = new_sl_price or position.sl_level
        amount = position.order.get("amount") or (abs(position.notional) / position.entry_price)

        if is_native:
            self.logger.info(f"🔄 Re-creating Native OCO bracket for {symbol} (Modification)")

            # 1. Cancel existing Native OCO
            await self.cancel_order(position.exchange_tp_id, symbol)

            # 2. Create new Native OCO bracket
            oco_result = await self.adapter.create_native_oco_bracket(
                symbol=symbol,
                side=position.side,
                amount=amount,
                tp_price=tp_price,
                sl_price=sl_price,
                params={"client_order_id": f"OMOD_{trade_id}_{uuid.uuid4().hex[:4]}"},
            )

            # Update position IDs
            native_id = oco_result.get("id") or oco_result.get("order_id")
            position.tp_order_id = native_id
            position.exchange_tp_id = native_id
            position.sl_order_id = native_id
            position.exchange_sl_id = native_id
            position.tp_level = tp_price
            position.sl_level = sl_price

            self.tracker._trigger_state_change()
            return {"status": "success", "native_id": native_id}
        else:
            # Manual OCO modification (fallback)
            self.logger.info(f"🔄 Modifying Manual OCO bracket for {symbol}")

            results = {"status": "success"}

            results = {"status": "success"}

            # --- TAKE PROFIT AMENDMENT ---
            if new_tp_price and new_tp_price != position.tp_level:
                # 1. SET STATE LOCK
                old_status = position.status
                position.status = "MODIFYING"

                try:
                    self.logger.info(f"🔄 Replacing TP for {symbol} ({position.exchange_tp_id} -> {new_tp_price})")
                    # Cancel old TP
                    if position.exchange_tp_id:
                        await self.cancel_order(position.exchange_tp_id, symbol)

                    # Create new TP
                    tp_order = await self._create_tp_order(symbol, position.side, amount, new_tp_price)
                    tp_id = tp_order.get("order_id") or tp_order.get("id")

                    # Update state
                    position.tp_order_id = tp_order.get("client_order_id") or tp_id
                    position.exchange_tp_id = tp_id
                    position.tp_level = new_tp_price
                    results["tp_id"] = tp_id
                finally:
                    # 2. RELEASE STATE LOCK
                    position.status = old_status

            # --- STOP LOSS AMENDMENT ---
            if new_sl_price and new_sl_price != position.sl_level:
                # 1. SET STATE LOCK
                old_status = position.status
                position.status = "MODIFYING"

                try:
                    self.logger.info(f"🔄 Replacing SL for {symbol} ({position.exchange_sl_id} -> {new_sl_price})")
                    # Cancel old SL
                    if position.exchange_sl_id:
                        await self.cancel_order(position.exchange_sl_id, symbol)

                    # Create new SL
                    sl_order = await self._create_sl_order(symbol, position.side, amount, new_sl_price)
                    sl_id = sl_order.get("order_id") or sl_order.get("id")

                    # Update state
                    position.sl_order_id = sl_order.get("client_order_id") or sl_id
                    position.exchange_sl_id = sl_id
                    position.sl_level = new_sl_price
                    results["sl_id"] = sl_id
                finally:
                    # 2. RELEASE STATE LOCK
                    position.status = old_status

            # Re-register OCO pair if both IDs exist and are separate
            if (
                not is_native
                and position.exchange_tp_id
                and position.exchange_sl_id
                and position.exchange_tp_id != position.exchange_sl_id
            ):
                await self.adapter.register_oco_pair(symbol, position.exchange_tp_id, position.exchange_sl_id)

            self.tracker._trigger_state_change()
            return results

    async def _execute_main_order(self, order: Dict[str, Any], client_order_id: str = None) -> Dict[str, Any]:
        """Execute main market order."""
        # Convert from trading order to exchange order format
        exchange_order = {
            "symbol": order["symbol"],
            "type": "market",
            "side": "buy" if order["side"] == "LONG" else "sell",
            "amount": order.get("amount", 0),  # Will be calculated by Croupier
            "params": {"client_order_id": client_order_id} if client_order_id else {},
        }

        return await self.executor.execute_market_order(exchange_order, timeout=30.0)

    async def _wait_for_fill(
        self, order_id: str, symbol: str, timeout: float = 30.0, future: asyncio.Future = None
    ) -> Dict[str, Any]:
        """
        Wait for order fill confirmation via WebSocket Event (Zero-API usage).
        Falls back to single API check if event missed.

        Args:
            order_id: Numeric Order ID or Client Order ID
            symbol: Trading symbol
            timeout: Max time to wait
            future: Optional future if already registered

        Returns:
            Full Fill data dict (to extract price and fee)

        Raises:
            TimeoutError: If fill not confirmed within timeout
        """
        if not future:
            # Register if not already done
            future = asyncio.Future()
            self.pending_orders[order_id] = future

        # Start polling task as backup (every 3s)
        poll_task = asyncio.create_task(self._poll_for_fill(order_id, symbol, future))

        try:
            # Wait for WS result
            fill_data = await asyncio.wait_for(future, timeout=timeout)
            return fill_data
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Fallback to REST check
            self.logger.warning(f"🕒 Timeout waiting for WS fill ({order_id}). Falling back to REST...")
            try:
                order_info = await self.adapter.fetch_order(order_id, symbol)
                if order_info.get("status") in ("closed", "filled"):
                    return order_info
            except Exception as e:
                self.logger.error(f"❌ REST fallback failed for {order_id}: {e}")

            raise TimeoutError(f"Order {order_id} not filled within {timeout}s")
        finally:
            poll_task.cancel()
            # Cleanup
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]

    async def _poll_for_fill(self, order_id: str, symbol: str, future: asyncio.Future):
        """Periodically check order status via REST API as a fallback."""
        while not future.done():
            await asyncio.sleep(3.0)  # Check every 3 seconds
            try:
                order_info = await self.adapter.fetch_order(order_id, symbol)
                if order_info.get("status") in ("closed", "filled"):
                    if not future.done():
                        future.set_result(order_info)
                        self.logger.info(f"✅ Order {order_id} fill confirmed via REST Polling")
                        break
            except Exception as e:
                self.logger.debug(f"Polling check failed for {order_id}: {e}")
                order_info = await self.adapter.fetch_order(order_id, symbol)
                status = order_info.get("status", "").lower()
                if status == "closed":
                    fill_price = float(order_info.get("average") or order_info.get("price") or 0)
                    if fill_price > 0 and not future.done():
                        self.logger.info(f"✅ Polling found fill for {order_id} @ {fill_price}")
                        future.set_result(fill_price)
                        return

    def _calculate_tp_sl_prices(
        self, entry_price: float, side: str, tp_pct: float, sl_pct: float, symbol: str
    ) -> tuple[float, float]:
        """
        Calculate absolute TP/SL prices from percentages.

        Args:
            entry_price: Entry price
            side: "LONG" or "SHORT"
            tp_pct: TP percentage (e.g., 0.01 for 1%)
            sl_pct: SL percentage (e.g., 0.01 for 1%)
            symbol: Trading symbol (for precision formatting)

        Returns:
            (tp_price, sl_price) tuple with proper tick size precision
        """
        if side == "LONG":
            tp_price = entry_price * (1 + tp_pct)
            sl_price = entry_price * (1 - sl_pct)
        else:  # SHORT
            tp_price = entry_price * (1 - tp_pct)
            sl_price = entry_price * (1 + sl_pct)

        # Apply exchange precision (tick size) to avoid "Price not increased by tick size" error
        tp_price = float(self.adapter.price_to_precision(symbol, tp_price))
        sl_price = float(self.adapter.price_to_precision(symbol, sl_price))

        if tp_price <= 0 or sl_price <= 0:
            self.logger.error(
                f"🚨 PRECISION ERROR: Rounded price is 0.0 for {symbol}! "
                f"TickSize might be too large for price {entry_price}"
            )

        return tp_price, sl_price

    async def cancel_order(self, order_id: str, symbol: str) -> None:
        """Cancel a single order with retry logic."""
        cancel_retry_config = RetryConfig(max_retries=3, backoff_base=0.3, backoff_factor=2.0, jitter=True)
        # Use symbol-specific breaker to isolate network issues
        await self.error_handler.execute_with_breaker(
            f"oco_cancel_{symbol}",
            self.adapter.cancel_order,
            order_id,
            symbol,
            retry_config=cancel_retry_config,
            timeout=15.0,
        )
        self.logger.info(f"✅ Cancelled order: {order_id}")

    async def create_tp_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        tp_price: float,
        trade_id: str = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create take profit limit order with retry logic and ReduceOnly handling."""
        return await self._create_tp_order(symbol, side, amount, tp_price, timeout)

    async def create_sl_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        sl_price: float,
        trade_id: str = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Create stop loss order with retry logic and ReduceOnly handling."""
        return await self._create_sl_order(symbol, side, amount, sl_price, timeout)

    async def _create_tp_order(
        self, symbol: str, side: str, amount: float, tp_price: float, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create take profit limit order with retry logic and ReduceOnly handling."""
        # TP is opposite side of entry
        tp_side = "sell" if side == "LONG" else "buy"

        self.logger.info(f"📈 Creating TP order @ {tp_price}")

        # =========================================================
        # NOTIONAL PRE-CHECK
        # If notional (price × amount) < exchange minimum, Binance rejects.
        # Fallback to closePosition=True which closes full position.
        # =========================================================
        notional = amount * tp_price
        connector = getattr(self.adapter, "connector", None) or getattr(self.adapter, "_connector", None)
        min_notional = 20.0  # Default for testnet
        if connector and hasattr(connector, "get_min_notional"):
            min_notional = connector.get_min_notional(symbol)

        use_close_position = notional < min_notional
        if use_close_position:
            self.logger.warning(f"⚠️ Notional ${notional:.2f} < min ${min_notional}. Using closePosition for TP.")

        async def _smart_execute_tp():
            nonlocal amount
            try:
                if use_close_position:
                    # Use TAKE_PROFIT_MARKET with closePosition=True for small notionals
                    # LIMIT orders with closePosition are invalid
                    return await self.executor.execute_order(
                        symbol=symbol,
                        side=tp_side,
                        amount=0,  # Ignored with closePosition
                        price=None,  # Market order doesn't have price
                        order_type="TAKE_PROFIT_MARKET",
                        params={
                            "closePosition": True,
                            "stopPrice": tp_price,
                            "workingType": "MARK_PRICE",
                            "clientOrderId_prefix": "TP",
                        },
                    )
                else:
                    return await self.executor.execute_limit_order(
                        symbol=symbol,
                        side=tp_side,
                        amount=amount,
                        price=tp_price,
                        params={"reduceOnly": True, "clientOrderId_prefix": "TP"},
                    )

            except Exception as e:
                # Handle ReduceOnly rejection (-2022), Invalid Amount (-4118), or MinNotional (-4164)
                # -4164 often appears if amount mismatch causes "dust" remaining or precision calculation issues
                err_str = str(e)
                if "-2022" in err_str or "-4118" in err_str or "-4164" in err_str:
                    self.logger.warning(f"⚠️ Limit TP rejected ({err_str}) for {symbol}. Checking position...")

                    # Verify actual position
                    try:
                        positions = await self.adapter.fetch_positions(symbol)
                        # Filter for this symbol and correct side
                        # Note: fetch_positions might return list of all or list of one
                        current_pos = None
                        for p in positions:
                            if p["symbol"] == symbol:
                                # Standardize field names
                                pos_amt = float(p.get("contracts") or p.get("positionAmt") or 0)
                                if (side == "LONG" and pos_amt > 0) or (side == "SHORT" and pos_amt < 0):
                                    current_pos = abs(pos_amt)
                                    break

                        if not current_pos or current_pos == 0:
                            self.logger.error(f"❌ Position for {symbol} is CLOSED. Aborting TP creation.")
                            # Raise specific error to stop retries
                            raise OCOAtomicityError(f"Position closed before TP creation: {e}")

                        if current_pos != amount:
                            self.logger.warning(
                                f"⚠️ Position size mismatch. Expected {amount}, Got {current_pos}. Adjusting..."
                            )
                            amount = current_pos
                            # Retry immediately with new amount
                            return await self.executor.execute_limit_order(
                                symbol=symbol,
                                side=tp_side,
                                amount=amount,
                                price=tp_price,
                                params={"reduceOnly": True, "clientOrderId_prefix": "TP"},
                            )

                    except Exception as fetch_err:
                        self.logger.error(f"❌ Failed to fetch position during recovery: {fetch_err}")
                        raise e  # Raise original error

                # Re-raise strictly if not handled
                raise e

        # Use symbol-specific breaker for TP
        return await self.error_handler.execute_with_breaker(
            f"oco_tp_{symbol}",
            _smart_execute_tp,
            retry_config=self.tpsl_retry_config,
            timeout=timeout,
        )

    async def _create_sl_order(
        self, symbol: str, side: str, amount: float, sl_price: float, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create stop loss order with retry logic and ReduceOnly handling."""
        # SL is opposite side of entry
        sl_side = "sell" if side == "LONG" else "buy"

        self.logger.info(f"📉 Creating SL order @ stop {sl_price}")

        # =========================================================
        # NOTIONAL PRE-CHECK
        # If notional (price × amount) < exchange minimum, Binance rejects.
        # Fallback to closePosition=True which closes full position.
        # =========================================================
        notional = amount * sl_price
        connector = getattr(self.adapter, "connector", None) or getattr(self.adapter, "_connector", None)
        min_notional = 20.0  # Default for testnet
        if connector and hasattr(connector, "get_min_notional"):
            min_notional = connector.get_min_notional(symbol)

        use_close_position = notional < min_notional
        if use_close_position:
            self.logger.warning(f"⚠️ Notional ${notional:.2f} < min ${min_notional}. Using closePosition for SL.")

        async def _smart_execute_sl():
            nonlocal amount
            try:
                # Inner execution
                if use_close_position:
                    result = await self.executor.execute_stop_order(
                        symbol=symbol,
                        side=sl_side,
                        amount=0,  # Ignored with closePosition
                        stop_price=sl_price,
                        params={"closePosition": True, "clientOrderId_prefix": "SL"},
                    )
                else:
                    result = await self.executor.execute_stop_order(
                        symbol=symbol,
                        side=sl_side,
                        amount=amount,
                        stop_price=sl_price,
                        params={"reduceOnly": True, "clientOrderId_prefix": "SL"},
                    )

                # Check for immediate zombie status (e.g. ReduceOnly race condition)
                status = str(result.get("status", "")).lower()
                if status in ["expired", "rejected", "canceled"]:
                    # Raising exception forces logic below or breaker retry
                    raise RuntimeError(f"SL Order rejected by exchange immediately (Status: {status})")

                return result

            except Exception as e:
                # Handle ReduceOnly rejection (Code -2022 or -4118) or immediate rejection
                if "-2022" in str(e) or "-4118" in str(e) or "rejected" in str(e).lower():
                    self.logger.warning(f"⚠️ SL rejected for {symbol}. Checking position...")

                    try:
                        positions = await self.adapter.fetch_positions(symbol)
                        current_pos = None
                        for p in positions:
                            if p["symbol"] == symbol:
                                pos_amt = float(p.get("contracts") or p.get("positionAmt") or 0)
                                if (side == "LONG" and pos_amt > 0) or (side == "SHORT" and pos_amt < 0):
                                    current_pos = abs(pos_amt)
                                    break

                        if not current_pos or current_pos == 0:
                            self.logger.error(f"❌ Position for {symbol} is CLOSED. Aborting SL creation.")
                            raise OCOAtomicityError(f"Position closed before SL creation: {e}")

                        if current_pos != amount:
                            self.logger.warning(
                                f"⚠️ Position size mismatch. Expected {amount}, Got {current_pos}. Adjusting..."
                            )
                            amount = current_pos
                            # Retry immediately with new amount
                            return await self.executor.execute_stop_order(
                                symbol=symbol,
                                side=sl_side,
                                amount=amount,
                                stop_price=sl_price,
                                params={"reduceOnly": True, "clientOrderId_prefix": "SL"},
                            )

                    except Exception as fetch_err:
                        self.logger.error(f"❌ Failed to fetch position during recovery: {fetch_err}")

                # Re-raise original error
                raise e

        # Use symbol-specific breaker for SL
        try:
            return await self.error_handler.execute_with_breaker(
                f"oco_sl_{symbol}",
                _smart_execute_sl,
                retry_config=self.tpsl_retry_config,
            )
        except Exception as e:
            # Let the error propagate
            raise e

    def _validate_oco_complete(
        self, main_order: Optional[Dict], tp_order: Optional[Dict], sl_order: Optional[Dict]
    ) -> None:
        """
        Validate that all 3 orders exist.

        Raises:
            OCOAtomicityError: If any order is missing
        """
        if not main_order:
            raise OCOAtomicityError("Main order is missing")
        if not tp_order:
            raise OCOAtomicityError("TP order is missing")
        if not sl_order:
            raise OCOAtomicityError("SL order is missing")

        # Validate order IDs exist
        if not (main_order.get("order_id") or main_order.get("id")):
            raise OCOAtomicityError("Main order has no order_id")
        if not (tp_order.get("order_id") or tp_order.get("id")):
            raise OCOAtomicityError("TP order has no order_id")
        if not (sl_order.get("order_id") or sl_order.get("id")):
            raise OCOAtomicityError("SL order has no order_id")

        # STATUS CHECK (Prevent immediate expiry/rejection slipping through)
        # We allow 'filled' for main order, but TP/SL should be open/new.
        # Relaxed check: Just warn if not open? No, fail if rejected/expired/canceled.

        tp_status = str(tp_order.get("status", "")).lower()
        sl_status = str(sl_order.get("status", "")).lower()

        # Relaxed check: Just warn if not open? No, fail if rejected/expired/canceled.
        # If canceled/expired immediately, it's useless protection.
        invalid_statuses = ["canceled", "expired", "rejected"]

        if tp_status in invalid_statuses:
            raise OCOAtomicityError(f"TP order is {tp_status} immediately after creation")
        if sl_status in invalid_statuses:
            raise OCOAtomicityError(f"SL order is {sl_status} immediately after creation")

        self.logger.debug("✅ OCO validation passed: all 3 orders exist")

    async def _cleanup_partial_oco(
        self, main_order: Optional[Dict], tp_order: Optional[Dict], sl_order: Optional[Dict]
    ) -> None:
        """
        Cleanup partial OCO bracket on failure.

        Cancels any orders that were created before failure.
        CRITICAL: If main order is filled, we MUST close the position to prevent orphans.
        """
        self.logger.warning("🧹 Cleaning up partial OCO bracket...")

        orders_to_cancel = []

        # Get symbol from any available order
        symbol = None
        if main_order and main_order.get("symbol"):
            symbol = main_order["symbol"]
        elif tp_order and tp_order.get("symbol"):
            symbol = tp_order["symbol"]
        elif sl_order and sl_order.get("symbol"):
            symbol = sl_order["symbol"]

        if tp_order and tp_order.get("order_id"):
            orders_to_cancel.append(("TP", tp_order["order_id"]))
        if sl_order and sl_order.get("order_id"):
            orders_to_cancel.append(("SL", sl_order["order_id"]))

        # Check main order status
        main_order_filled = False
        if main_order:
            status = main_order.get("status")
            if status == "closed" or status == "FILLED":
                main_order_filled = True
            elif status != "canceled" and main_order.get("order_id"):
                # Open but not filled -> Cancel it
                orders_to_cancel.append(("Main", main_order["order_id"]))

        # 1. Cancel open orders (TP/SL/Main)
        # Use EMERGENCY BYPASS for cleanup to ensure we don't get blocked by breakers
        connector = getattr(self.adapter, "connector", None) or getattr(self.adapter, "_connector", None)
        if not connector:
            connector = self.adapter

        for order_type, order_id in orders_to_cancel:
            try:
                # Bypass ErrorHandler for emergency individual cancellation
                await connector.cancel_order(order_id, symbol)
                self.logger.info(f"✅ Cancelled {order_type} order: {order_id}")
            except Exception as e:
                self.logger.error(f"❌ Failed to cancel {order_type} order {order_id}: {e}")
                # CRITICAL FIX: If Main (MARKET) order fails to cancel, it means it probably filled.
                # We must trigger emergency close if it was a MARKET order.
                if order_type == "Main":
                    if main_order and main_order.get("type", "").lower() == "market":
                        self.logger.warning(f"⚠️ MARKET Main order {order_id} could not be cancelled. Assuming FILLED.")
                        main_order_filled = True

        # 2. EMERGENCY CLOSE if Main was filled
        if main_order_filled:
            self.logger.warning("🚨 Main order was FILLED but OCO failed! Closing position immediately...")
            try:
                # We need to close the position we just opened
                symbol = main_order.get("symbol") or symbol  # Fallback to symbol arg
                side = main_order.get("side")

                # Get actual filled amount if possible, else order amount
                amount = float(main_order.get("filled") or main_order.get("amount") or 0)

                if amount <= 0:
                    self.logger.error("❌ main_order_filled is True but amount is 0? Skipping emergency close.")
                    return

                # Reverse side
                close_side = "sell" if side.lower() == "buy" else "buy"

                # =========================================================
                # EMERGENCY BYPASS CHANNEL
                # Call connector DIRECTLY to bypass ErrorHandler/CircuitBreaker
                # This ensures emergency closes NEVER get blocked
                # =========================================================
                connector = getattr(self.adapter, "connector", None) or getattr(self.adapter, "_connector", None)
                if not connector:
                    # Fallback to adapter if connector not accessible
                    self.logger.warning("⚠️ Could not access raw connector, falling back to adapter")
                    connector = self.adapter

                self.logger.info(f"🛡️ EMERGENCY BYPASS: {close_side.upper()} market for {amount} {symbol}")

                try:
                    # First attempt: reduceOnly with exact amount
                    await connector.create_order(
                        symbol=symbol, side=close_side, amount=amount, order_type="market", params={"reduceOnly": True}
                    )
                    self.logger.info(f"✅ Emergency close successful for {symbol} {amount}")
                except Exception as first_error:
                    # Second attempt: closePosition (ignores quantity, closes everything)
                    self.logger.warning(f"⚠️ First attempt failed ({first_error}), trying closePosition...")
                    try:
                        await connector.create_order(
                            symbol=symbol,
                            side=close_side,
                            amount=0,  # Ignored when closePosition=True
                            order_type="market",
                            params={"closePosition": True},
                        )
                        self.logger.info(f"✅ Emergency close via closePosition successful for {symbol}")
                    except Exception as second_error:
                        self.logger.critical(
                            f"🔥 BOTH EMERGENCY CLOSE ATTEMPTS FAILED: "
                            f"1st: {first_error}, 2nd: {second_error} | MANUAL INTERVENTION REQUIRED!"
                        )

            except Exception as e:
                self.logger.critical(f"🔥 FAILED TO CLOSE ORPHANED POSITION: {e} | MANUAL INTERVENTION REQUIRED!")

        if orders_to_cancel or main_order_filled:
            self.logger.warning(
                f"🧹 Cleanup complete. Cancelled: {len(orders_to_cancel)}, Closed Position: {main_order_filled}"
            )

    async def cancel_bracket(self, tp_order_id: Optional[str], sl_order_id: Optional[str], symbol: str) -> None:
        """
        Cancel TP and SL orders for a position with retry logic in parallel.

        Args:
            tp_order_id: Take profit order ID to cancel
            sl_order_id: Stop loss order ID to cancel
            symbol: Trading symbol (e.g., 'BNB/USDT') - REQUIRED for multi-symbol mode
        """
        cancel_retry_config = RetryConfig(max_retries=3, backoff_base=0.3, backoff_factor=2.0, jitter=True)

        async def cancel_single(order_id, order_type):
            if not order_id:
                return
            try:
                # Use symbol-specific breaker for OCO cancel
                await self.error_handler.execute_with_breaker(
                    f"oco_cancel_{symbol}",
                    self.adapter.cancel_order,
                    order_id,
                    symbol,
                    retry_config=cancel_retry_config,
                    timeout=15.0,  # Upper bound to prevent shutdown hang
                )
                self.logger.info(f"✅ Cancelled {order_type} order: {order_id}")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to cancel {order_type} order {order_id}: {e}")

        # Parallelize TP and SL cancellation to halve shutdown time per position
        await asyncio.gather(cancel_single(tp_order_id, "TP"), cancel_single(sl_order_id, "SL"))
