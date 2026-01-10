"""
Croupier - Portfolio Orchestrator (Refactored).

Lightweight orchestrator that delegates to specialized components:
- OrderExecutor: Handles individual order execution
- OCOManager: Manages OCO bracket orders
- ReconciliationService: Syncs state with exchange

This replaces the 1911-line God Object with a clean facade pattern.

Author: Casino V3 Team
Version: 3.0.0
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from config import trading as trading_config
from core.error_handling import get_error_handler
from core.interfaces import TimeIterator
from core.observability.historian import historian

# Phase 31: OrderTracker removed - PositionTracker is now the single source of truth
from core.portfolio.balance_manager import BalanceManager
from core.portfolio.position_tracker import OpenPosition, PositionTracker
from utils.symbol_norm import normalize_symbol

from .components.exit_manager import ExitManager
from .components.oco_manager import OCOManager
from .components.order_executor import OrderExecutor
from .components.reconciliation_service import ReconciliationService


class Croupier(TimeIterator):
    """
    Portfolio orchestrator - delegates to specialized components.

    Components:
    - OrderExecutor: Execute individual orders with retry
    - OCOManager: Create OCO brackets atomically
    - ReconciliationService: Sync state with exchange
    - ExitManager: Handle dynamic exits (Trailing, Breakeven, Reversal)

    Example:
        adapter = ExchangeAdapter(connector, symbol="BTC/USDT:USDT")
        croupier = Croupier(adapter, initial_balance=10000.0)

        # Execute OCO bracket order
        result = await croupier.execute_order({
            "symbol": "BTC/USDT:USDT",
            "side": "LONG",
            "size": 0.01,
            "take_profit": 1.01,
            "stop_loss": 0.99
        })
    """

    def __init__(self, exchange_adapter, initial_balance: float, max_concurrent_positions: int = 10):
        """
        Initialize Croupier orchestrator.

        Args:
            exchange_adapter: ExchangeAdapter for order execution
            initial_balance: Starting capital
            max_concurrent_positions: Max number of concurrent positions
        """
        super().__init__()
        self.adapter = exchange_adapter
        # Backward compatibility: some components expect exchange_adapter
        self.exchange_adapter = exchange_adapter
        self.logger = logging.getLogger("Croupier")

        # Initialize core components
        self.error_handler = get_error_handler()
        self.balance_manager = BalanceManager(initial_balance)
        self.position_tracker = PositionTracker(
            max_concurrent_positions=max_concurrent_positions, adapter=exchange_adapter
        )

        # Phase 31: PositionTracker is now the single source of truth for order state
        # Initialize specialized components
        self.order_executor = OrderExecutor(exchange_adapter, self.error_handler)
        self.oco_manager = OCOManager(self.order_executor, self.position_tracker, exchange_adapter)

        # Legacy: Still keep reconciliation for Adopt/Cleanup logic, but without its own loop
        self.reconciliation = ReconciliationService(exchange_adapter, self.position_tracker, self.oco_manager)

        self.exit_manager = ExitManager(self)
        self.process_start_balance: float = 0.0
        self.is_drain_mode: bool = False
        self._drain_in_progress: bool = False  # Task guard for drain status updates
        self._last_funding_sync: float = 0.0  # Phase 30: For precision accounting

        self.logger.info(
            f"[CORE] ✅ Croupier V4 initialized | Balance: {initial_balance} | "
            f"Max Positions: {max_concurrent_positions}"
        )

    def set_drain_mode(self, enabled: bool):
        """Enable or disable drain mode (no new entries, narrow exits)."""
        self.is_drain_mode = enabled

        # Bypass circuit breakers during draining to ensure exit attempts continue
        self.error_handler.set_shutdown_mode(enabled)

        if enabled:
            self.logger.warning("[CORE] 🕒 Croupier entering DRAIN MODE. Narrowing TPs for all positions.")

    async def _apply_drain_phase(self, phase: str):
        """Helper to apply a drain phase to all active positions."""
        # Fix: PositionTracker uses a list 'open_positions', not a dict
        active_positions = list(self.position_tracker.open_positions)
        if not active_positions:
            return

        self.logger.info(f"⏳ Drain Phase: {phase} | Positions: {len(active_positions)}")

        # Limit concurrency to prevent Circuit Breaker trips (Burst protection)
        sem = asyncio.Semaphore(2)

        async def _apply_with_limit(pos):
            async with sem:
                await self.exit_manager.apply_dynamic_exit(pos, phase)

        tasks = [_apply_with_limit(pos) for pos in active_positions]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def update_drain_status(self, remaining_minutes: float):
        """
        Periodically called during drain phase to trigger progressive exits.

        Schedule (T-30m window):
        - T-30m to T-20m: OPTIMISTIC (50% TP)
        - T-20m to T-10m: DEFENSIVE (Break Even)
        - T-10m to T-5m:  AGGRESSIVE (Small Loss)
        - T-5m to T-0m:   PANIC (Market Close)
        """
        if not self.is_drain_mode or self._drain_in_progress:
            return

        try:
            self._drain_in_progress = True

            # Determine Phase based on window ratio
            ratio = remaining_minutes / trading_config.DRAIN_PHASE_MINUTES

            if ratio <= 0.16:  # Last 5m of a 30m window
                phase = "PANIC"
            elif ratio <= 0.33:  # Last 10m of a 30m window
                phase = "AGGRESSIVE"
            elif ratio <= 0.66:  # Last 20m of a 30m window
                phase = "DEFENSIVE"
            else:
                phase = "OPTIMISTIC"

            # Apply Phase logic
            await self._apply_drain_phase(phase)

        except Exception as e:
            self.logger.error(f"❌ Error in update_drain_status: {e}")
        finally:
            self._drain_in_progress = False

    async def modify_tp(
        self,
        trade_id: str,
        new_tp_price: float,
        symbol: str,
        old_tp_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Modify Take Profit for a position using the unified OCOManager."""
        self.logger.info(f"🔄 Modifying TP for {trade_id} | New TP: {new_tp_price:.2f}")

        try:
            result = await self.oco_manager.modify_bracket(
                trade_id=trade_id, symbol=symbol, new_tp_price=new_tp_price, timeout=trading_config.GRACEFUL_TP_TIMEOUT
            )

            if result.get("status") == "success":
                # Reconciliation for manual fallback safety
                if "tp_id" in result:
                    import asyncio

                    asyncio.create_task(self.reconcile_positions(symbol))

                return {
                    "status": "success",
                    "new_order_id": result.get("native_id") or result.get("tp_id"),
                    "new_tp_price": new_tp_price,
                }
            return result

        except Exception as e:
            self.logger.error(f"❌ Failed to modify TP: {e}")
            raise e

    async def execute_order(self, order: Dict[str, Any], wait_for_fill: bool = False) -> Dict[str, Any]:
        """
        Execute order with full OCO bracket.

        This is the main entry point for creating new positions.
        Delegates to OCOManager for atomic bracket creation.

        Args:
            order: Order dict with:
                - symbol: Trading symbol
                - side: "LONG" or "SHORT"
                - size: Position size fraction (e.g., 0.05 = 5% of equity)
                - amount: Order amount in contracts (optional, calculated from size if missing)
                - take_profit: TP multiplier
                - stop_loss: SL multiplier
            wait_for_fill: Wait for main order fill confirmation (default: False for speed)

        Returns:
            OCO result dict with main_order, tp_order, sl_order

        Raises:
            OCOAtomicityError: If OCO creation fails
        """
        # 0. NORMALIZE SYMBOL
        raw_symbol = order.get("symbol", "")
        symbol = normalize_symbol(raw_symbol)
        order["symbol"] = symbol

        # DRAIN MODE CHECK
        if self.is_drain_mode:
            self.logger.warning(f"🚫 Drain Mode Active: Rejecting new entry for {symbol}")
            return {"status": "error", "message": "Drain mode active"}

        # 1. Execute OCO bracket order
        self.logger.info(f"📥 Execute order request: {order['side']} {order['symbol']}")

        # Extract contributors (sensor IDs) for tracking
        contributors = order.get("contributors", [])

        # Calculate amount from size if not provided
        if "amount" not in order or order.get("amount") == 0:
            if "size" in order:
                # size is a fraction of equity (e.g., 0.05 = 5%)
                current_equity = self.get_equity()

                # SIZING LOGIC
                # Mode 1: Fixed Notional (Default) -> Size = Equity * Bet_Size
                # Mode 2: Fixed Risk -> Size = (Equity * Bet_Size) / SL_Distance
                sizing_mode = getattr(trading_config, "POSITION_SIZING_MODE", "FIXED_NOTIONAL")

                if sizing_mode == "FIXED_RISK":
                    stop_loss_pct = order.get("stop_loss", trading_config.STOP_LOSS)
                    risk_amount = current_equity * order["size"]

                    if stop_loss_pct <= 0:
                        raise ValueError("Fixed Risk Sizing requires positive Stop Loss %")

                    position_value = risk_amount / stop_loss_pct
                    self.logger.info(
                        f"⚖️ Fixed Risk Sizing: Risk={risk_amount:.2f} ({order['size']:.2%}) | SL={stop_loss_pct:.2%} | Notional={position_value:.2f}"
                    )

                else:  # FIXED_NOTIONAL
                    position_value = current_equity * order["size"]

                # Get current price (with retry for transient errors)
                from core.error_handling import RetryConfig

                current_price = await self.error_handler.execute_with_breaker(
                    f"get_price_{order['symbol']}",
                    self.exchange_adapter.get_current_price,
                    order["symbol"],
                    retry_config=RetryConfig(max_retries=3, backoff_base=0.5, backoff_max=5.0),
                )

                # Calculate amount in contracts
                amount_raw = position_value / current_price

                # Round to exchange precision
                amount = float(self.exchange_adapter.amount_to_precision(order["symbol"], amount_raw))

                # Validate minimum amount
                if amount <= 0:
                    raise ValueError(
                        f"Order too small after precision rounding ({sizing_mode}): "
                        f"raw={amount_raw:.12f} → rounded={amount:.8f} | "
                        f"Equity={current_equity:.2f} | Size={order['size']:.2%}"
                    )

                # Add calculated amount to order
                order = order.copy()
                order["amount"] = amount

                self.logger.info(
                    f"📊 Calculated order amount ({sizing_mode}): Equity={current_equity:.2f} | "
                    f"Size={order['size']:.2%} | Value={position_value:.2f} | "
                    f"Price={current_price:.2f} | Amount={amount:.8f}"
                )
            else:
                raise ValueError("Order must have either 'amount' or 'size'")

        # Delegate to OCOManager (don't wait for fill in demo/live, market orders are instant)
        result = await self.oco_manager.create_bracketed_order(
            order, wait_for_fill=wait_for_fill, contributors=contributors
        )

        # Position is already registered by OCOManager
        position = result.get("position")
        if not position:
            # Fallback if OCOManager didn't return position (shouldn't happen with new code)
            self.logger.warning("⚠️ OCOManager didn't return position, attempting manual registration")
            position = await self._register_position(order, result)

        # Update balance (reserve margin)
        margin_used = order.get("margin_used", 0)
        if margin_used > 0:
            self.balance_manager.reserve_margin(margin_used)

        self.logger.info(f"✅ Position opened: {position.trade_id} | " f"Entry: {result['fill_price']:.2f}")

        return result

    async def close_position(
        self,
        trade_id: str,
        exit_reason: str = "MANUAL",
        position_obj: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Close a position manually.

        1. Cancel TP/SL orders
        2. Execute market close order
        """
        # Find position
        position = position_obj
        if not position:
            for pos in self.position_tracker.open_positions:
                if pos.trade_id == trade_id:
                    position = pos
                    break

        if not position:
            raise ValueError(f"Position not found: {trade_id}")

        self.logger.info(f"📤 Closing position: {trade_id} | {position.symbol} {position.side}")

        # State Machine: Mark as CLOSING to prevent reconciliation interference
        position.status = "CLOSING"
        self.position_tracker._trigger_state_change()

        # 1. Cancel TP/SL
        await self.oco_manager.cancel_bracket(position.tp_order_id, position.sl_order_id, position.symbol)

        # 2. Execute market close
        close_side = "sell" if position.side == "LONG" else "buy"

        # Calculate amount (use remaining amount if partial fills supported, but for now full close)
        # We need to use the original amount or current size.
        # Fallback logic for reconciled positions that lack 'order' history.
        amount = position.order.get("amount")

        if not amount:
            # Fallback 1: Try getting from raw exchange info (most accurate)
            if hasattr(position, "info") and position.info and "positionAmt" in position.info:
                try:
                    amount = abs(float(position.info["positionAmt"]))
                except (ValueError, TypeError):
                    pass

        if not amount:
            # Fallback 2: Calculate from Notional / Entry Price
            if position.entry_price > 0 and position.notional:
                amount = abs(position.notional) / position.entry_price

        if not amount:
            # Fallback 3: Raise error if strictly impossible to determine
            raise ValueError(
                f"Position {trade_id} has no amount information (Order missing, Info missing, Calc failed)"
            )

        close_order = {
            "symbol": position.symbol,
            "side": close_side,
            "type": "market",
            "amount": amount,
            "params": {},  # Removed reduceOnly to avoid -2022 error
        }

        self.logger.info(f"📉 Sending close order: {close_side} {amount} {position.symbol}")

        try:
            result = await self.order_executor.execute_market_order(close_order, timeout=30.0)
        except Exception as e:
            # Fallback for Binance PERCENT_PRICE filter error (-4131)
            # This happens when Market orders are blocked due to volatility/wicks
            if "-4131" in str(e):
                self.logger.warning(
                    f"⚠️ Caught PERCENT_PRICE error (-4131) for {position.symbol}. Initiating Smart Close Fallback..."
                )
                try:
                    # Fetch fresh price
                    current_price = await self.adapter.get_current_price(position.symbol)

                    # TIER 1: User Strategy - Aggressive Marketable Limit (simulates Market)
                    # Try 5% buffer to force immediate fill against book
                    buffer = 0.95 if close_side.lower() == "sell" else 1.05
                    limit_price = current_price * buffer
                    limit_price = float(self.adapter.price_to_precision(position.symbol, limit_price))

                    self.logger.info(
                        f"🔄 Fallback Tier 1: Sending Aggressive LIMIT {close_side} @ {limit_price} (5% buffer)"
                    )

                    try:
                        result = await self.order_executor.execute_limit_order(
                            symbol=position.symbol, side=close_side, amount=amount, price=limit_price
                        )
                        self.logger.info(f"✅ Aggressive LIMIT successful: {result.get('order_id')}")

                    except Exception as tier1_e:
                        # TIER 2: Band-Compliant Limit (Regex Extraction)
                        # If Aggressive Limit fails due to price band (-4016), we must respect the hard limit
                        err_str = str(tier1_e)
                        if "-4016" in err_str or "Limit price can't be" in err_str:
                            self.logger.warning(
                                f"⚠️ Aggressive Limit rejected by band ({err_str}). Attempting Tier 2 (Exact Band)..."
                            )

                            import re

                            match_high = re.search(r"higher than ([\d\.]+)", err_str)
                            match_low = re.search(r"lower than ([\d\.]+)", err_str)

                            target_price = None
                            if match_high:
                                # Buying: Max price is X. We want to buy as high as possible -> X * 0.999
                                target_price = float(match_high.group(1).rstrip(".")) * 0.999
                            elif match_low:
                                # Selling: Min price is Y. We want to sell as low as possible -> Y * 1.001
                                target_price = float(match_low.group(1).rstrip(".")) * 1.001

                            if target_price:
                                target_price = float(self.adapter.price_to_precision(position.symbol, target_price))
                                self.logger.info(
                                    f"🔄 Fallback Tier 2: Sending Band-Compliant LIMIT {close_side} @ {target_price}"
                                )

                                result = await self.order_executor.execute_limit_order(
                                    symbol=position.symbol, side=close_side, amount=amount, price=target_price
                                )
                                self.logger.info(f"✅ Band LIMIT successful: {result.get('order_id')}")
                            else:
                                raise tier1_e  # Cannot parse, raise original
                        else:
                            raise tier1_e  # Not a band error, raise original

                except Exception as fallback_e:
                    self.logger.error(f"❌ All Smart Close strategies failed: {fallback_e}")
                    raise e  # Raise ORIGINAL error (Market fail) to keep logs clean upstream
            else:
                raise e

        fill_price = float(result.get("average", 0) or result.get("price", 0))

        # FIX: Prevent 0.0 fill price from destroying PnL
        if fill_price <= 0:
            self.logger.warning(
                f"⚠️ Order result missing fill price (Got {fill_price}). Fetching current price for PnL estimation..."
            )
            try:
                fill_price = await self.adapter.get_current_price(position.symbol)
                self.logger.info(f"✅ Fetched fallback price: {fill_price}")
            except Exception as e:
                self.logger.error(f"❌ Failed to fetch current price for fallback: {e}")
                # Fallback to entry price to avoid massive PnL spike (neutral exit)
                fill_price = position.entry_price

        self.logger.info(f"✅ Position closed: {trade_id} | Fill: {fill_price}")

        # Manually confirm close in tracker since we initiated it
        # Calculate PnL
        if position.side == "LONG":
            pnl = (fill_price - position.entry_price) * position.notional / position.entry_price
        else:
            pnl = (position.entry_price - fill_price) * position.notional / position.entry_price

        # PHASE 30: FORENSIC FEE ENRICHMENT
        # Fetch real exit fee from the exchange to ensure accurate accounting
        real_fee = 0.0
        try:
            await asyncio.sleep(0.5)  # Allow exchange to index the trade
            trades = await self.adapter.fetch_my_trades(position.symbol, limit=3)
            if trades:
                trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                real_fee = float(trades[0].get("fee", {}).get("cost", 0) or 0)
                self.logger.info(f"💰 Enriched close for {trade_id}: exit_fee={real_fee:.4f}")
        except Exception as enrich_e:
            self.logger.warning(f"⚠️ Could not enrich exit fee for {trade_id}: {enrich_e}")

        self.position_tracker.confirm_close(
            trade_id=trade_id,
            exit_price=fill_price,
            exit_reason=exit_reason,
            pnl=pnl,
            fee=real_fee,
        )

        return result

    async def modify_sl(
        self,
        trade_id: str,
        new_sl_price: float,
        symbol: str,
        old_sl_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Modify Stop Loss for a position using the unified OCOManager."""
        self.logger.info(f"🔄 Modifying SL for {trade_id} | New SL: {new_sl_price:.2f}")

        try:
            result = await self.oco_manager.modify_bracket(
                trade_id=trade_id, symbol=symbol, new_sl_price=new_sl_price, timeout=trading_config.GRACEFUL_SL_TIMEOUT
            )

            if result.get("status") == "success":
                # Reconciliation as a safety measure for manual fallback
                if "sl_id" in result:
                    import asyncio

                    asyncio.create_task(self.reconcile_positions(symbol))

                return {
                    "status": "success",
                    "new_order_id": result.get("native_id") or result.get("sl_id"),
                    "new_sl_price": new_sl_price,
                }
            return result

        except Exception as e:
            self.logger.error(f"❌ Failed to modify SL: {e}")
            raise e

    async def reconcile_positions(self, symbol: Optional[str] = None):
        """
        Reconcile positions with exchange.

        Args:
            symbol: Symbol to reconcile (None = all symbols)

        Returns:
            Reconciliation report
        """
        if symbol:
            return await self.reconciliation.reconcile_symbol(symbol)
        else:
            # Reconcile all symbols in a single optimized pass
            return await self.reconciliation.reconcile_all()

    def get_balance(self) -> float:
        """Get current available balance."""
        return self.balance_manager.balance

    def get_equity(self) -> float:
        """Get current equity (balance + unrealized PnL)."""
        return self.balance_manager.equity

    def get_open_positions(self) -> List[OpenPosition]:
        """Get all open positions."""
        return self.position_tracker.open_positions

    def can_open_position(self, margin_required: float) -> bool:
        """Check if we can open a new position."""
        return self.balance_manager.can_open_position(margin_required)

    def is_pending(self, symbol: str) -> bool:
        """Check if symbol has a pending OCO order (in-flight)."""
        # Delegated to OCOManager
        return symbol in self.oco_manager.pending_symbols

    async def _register_position(self, order: Dict[str, Any], oco_result: Dict[str, Any]) -> OpenPosition:
        """
        Register new position in tracker.

        Args:
            order: Original order dict
            oco_result: OCO creation result

        Returns:
            OpenPosition instance
        """
        # Calculate liquidation level (approximate)
        entry_price = oco_result["fill_price"]
        leverage = order.get("leverage", 1)
        side = order["side"]

        liquidation_level = None
        if leverage > 0:
            if side == "LONG":
                liquidation_level = entry_price * (1.0 - (1.0 / leverage) + 0.005)
            elif side == "SHORT":
                liquidation_level = entry_price * (1.0 + (1.0 / leverage) - 0.005)

        # Create position object
        position = OpenPosition(
            trade_id=oco_result["main_order"]["order_id"],
            symbol=order["symbol"],
            side=order["side"],
            entry_price=entry_price,
            entry_timestamp=oco_result["main_order"].get("timestamp", ""),
            margin_used=order.get("margin_used", 0),
            notional=order.get("notional", 0),
            leverage=leverage,
            tp_level=oco_result["tp_price"],
            sl_level=oco_result["sl_price"],
            liquidation_level=liquidation_level,
            order=order,
            main_order_id=oco_result["main_order"]["order_id"],
            tp_order_id=oco_result["tp_order"].get("client_order_id"),
            sl_order_id=oco_result["sl_order"].get("client_order_id"),
            exchange_tp_id=oco_result["tp_order"].get("order_id"),
            exchange_sl_id=oco_result["sl_order"].get("order_id"),
        )

        # Add to tracker
        self.position_tracker.open_positions.append(position)
        self.position_tracker.total_trades_opened += 1

        # Update granular counters (Critical for Session Report)
        if position.side == "LONG":
            self.position_tracker.new_longs += 1
        else:
            self.position_tracker.new_shorts += 1

        # Trigger state save
        self.position_tracker._trigger_state_change()

        return position

    def get_stats(self) -> Dict[str, Any]:
        """
        Get trading statistics.

        Returns:
            Dict with stats from position tracker
        """
        return self.position_tracker.get_stats()

    async def cleanup_symbol(self, symbol: str) -> None:
        """
        Cleanup all orders and positions for a symbol.

        Args:
            symbol: Symbol to cleanup
        """
        self.logger.info(f"🧹 Cleaning up symbol {symbol}...")

        # 1. Cancel all open orders
        try:
            open_orders = await self.adapter.fetch_open_orders(symbol)
            for order in open_orders:
                await self.adapter.cancel_order(order["id"], symbol)
            self.logger.info(f"✅ Cancelled {len(open_orders)} open orders for {symbol}")
        except Exception as e:
            self.logger.error(f"❌ Error cancelling open orders for {symbol}: {e}")

        # 2. Close any remaining positions (if not handled by main loop)
        # Note: main.py attempts to close positions via close_position before calling this,
        # but this serves as a final safety net or for untracked positions.
        try:
            # We can use reconciliation service to find and close untracked positions
            await self.reconciliation.reconcile_symbol(symbol)
        except Exception as e:
            self.logger.error(f"❌ Error reconciling/cleaning positions for {symbol}: {e}")

    # =========================================================
    # V4 REACTOR INTERFACE (TimeIterator)
    # =========================================================

    @property
    def name(self) -> str:
        return "Croupier"

    async def start(self) -> None:
        """Start components."""
        self.logger.info("🛡️ Croupier Reactor Started")

    async def stop(self) -> None:
        """Stop components."""
        self.logger.info("🛑 Croupier Reactor Stopped")

    async def tick(self, timestamp: float) -> None:
        """
        Single tick entry point.
        Unifies all periodic activities.
        """
        # Phase 31: OrderTracker removed - PositionTracker handles order state

        # 2. Periodic Balance Sync (Every 5 mins)
        if int(timestamp) % 300 == 0:
            await self._sync_balance()

        # 2.5. Periodic Funding Sync (Every 10 mins) - Phase 30
        if timestamp - self._last_funding_sync >= 600:
            await self._sync_funding_fees()

        # 3. Dynamic Exits (If needed, can be driven here)
        # Note: In V3, ExitManager was likely driven by external ticks or own loop.
        # In V4, it should be driven here.
        # await self.exit_manager.tick(timestamp)

    async def _sync_balance(self):
        """Standardized balance sync."""
        try:
            exchange_balance = await self.adapter.fetch_balance()
            actual_equity = exchange_balance.get("total", {}).get("USDT", 0.0)
            if actual_equity > 0:
                self.balance_manager.set_balance(actual_equity)
                self.logger.info(f"[WALLET] ⚖️ Synced Balance: {actual_equity:.2f} USDT")
        except Exception as e:
            self.logger.error(f"❌ Balance sync failed: {e}")

    async def _sync_funding_fees(self):
        """
        Fetch and distribute funding fees to open positions.
        Ensures that 'Real PnL' includes interest costs.
        """
        if not self.adapter or not self.position_tracker.open_positions:
            return

        now = time.time()
        # Initial sync use 15m ago, subsequent syncs use last_sync_time
        # We add 1ms to startTime to avoid fetching the same record twice
        since = int(((self._last_funding_sync or (now - 900))) * 1000) + 1

        try:
            income_list = await self.adapter.fetch_income(income_type="FUNDING_FEE", since=since)
            self._last_funding_sync = now

            if not income_list:
                return

            # Group income by symbol
            symbol_totals = {}
            for item in income_list:
                symbol = self.adapter.denormalize_symbol(item["symbol"])
                income_val = float(item["income"])
                symbol_totals[symbol] = symbol_totals.get(symbol, 0.0) + income_val

            # Distribute to open positions
            for pos in self.position_tracker.open_positions:
                if pos.symbol in symbol_totals:
                    # income is negative for fees PAID, positive for fees RECEIVED.
                    # net_pnl = gross - exit_fee - entry_fee - funding_accrued
                    # So if income = -0.5 (payment out), funding_accrued should increase by 0.5.
                    net_cost = -symbol_totals[pos.symbol]
                    if abs(net_cost) > 1e-8:
                        pos.funding_accrued += net_cost
                        self.logger.info(
                            f"💰 Captured {net_cost:+.4f} funding for {pos.symbol} | Total: {pos.funding_accrued:.4f}"
                        )
        except Exception as e:
            self.logger.error(f"❌ Failed to sync funding fees: {e}")

    # =========================================================
    # PHASE 27: PERSISTENT ACCOUNTING & RECONCILIATION
    # =========================================================

    def _start_background_tasks(self):
        """Deprecated in V4 - use Clock instead."""
        pass

    def set_process_start_balance(self, balance: float):
        """Sets the exact balance at the start of this execution."""
        self.process_start_balance = float(balance)
        self.logger.info(f"[WALLET] 💰 Process Start Balance: {self.process_start_balance:.2f} USDT")

    def get_session_summary(self, final_balance: Optional[float] = None) -> Dict[str, Any]:
        """
        Get precise trade stats from Historian (Net PnL) and Account Delta.

        Args:
            final_balance: Optional real wallet balance at end of session.
                          If provided, calculates 'Leakage' (untracked pnl).
        """
        stats = historian.get_session_stats(session_id=self.position_tracker.session_id)

        # Calculate Transparency Metrics (Phase 30)
        strategy_net_pnl = stats.get("total_net_pnl", 0.0)

        # Robust conversion for final_balance (handle "N/A" or other non-numeric strings)
        try:
            final_bal_float = float(final_balance) if final_balance is not None else None
        except (ValueError, TypeError):
            final_bal_float = None

        if final_bal_float is not None and self.process_start_balance > 0:
            account_delta = final_bal_float - self.process_start_balance
            # Leakage = Actual change - Strategy PnL
            # This accounts for ghosts, funding, and other untracked adjustments
            leakage = account_delta - strategy_net_pnl
            verified = True
        else:
            account_delta = 0.0
            leakage = None  # Use None to indicate UNVERIFIED
            verified = False

        stats.update(
            {
                "account_delta": account_delta,
                "leakage": leakage,
                "audit_verified": verified,
                "start_balance": self.process_start_balance,
                "final_balance": final_bal_float if final_bal_float is not None else 0.0,
            }
        )

        return stats

    def reset_strategy_history(self):
        """Wipes persistent history - used when switching strategies."""
        self.logger.warning("🗑️ Strategy Reset: Wiping all persistent trade history!")
        historian.clear_history()
        # Also reset tracker counters for visual feedback
        self.position_tracker.total_trades_closed = 0
        self.position_tracker.total_wins = 0
        self.position_tracker.total_losses = 0
        self.position_tracker.total_trades_opened = 0
        self.position_tracker.new_longs = 0
        self.position_tracker.new_shorts = 0

    async def sweep_orphaned_orders(self) -> None:
        """
        Startup Sweep: Detect and clean up orphaned orders and unknown positions.

        Scans all symbols with activity (open orders or positions) and runs reconciliation.
        """
        self.logger.info("🧹 Starting global sweep of orphaned orders and positions...")

        try:
            active_symbols = set()

            # 1. Find symbols with open positions
            try:
                positions = await self.adapter.fetch_positions()
                for pos in positions:
                    if float(pos.get("size", 0)) > 0:
                        active_symbols.add(pos["symbol"])
            except Exception as e:
                self.logger.error(f"❌ Failed to fetch positions during sweep: {e}")

            # 2. Find symbols with open orders
            try:
                # Note: Some adapters might not support fetch_open_orders(None)
                # If so, we might miss orders on symbols without positions.
                # But for Binance Futures, it works.
                orders = await self.adapter.fetch_open_orders()
                for order in orders:
                    active_symbols.add(order["symbol"])
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to fetch all open orders during sweep (might need symbol): {e}")

            self.logger.info(f"🔍 Found activity on {len(active_symbols)} symbols: {active_symbols}")

            # 3. Reconcile each active symbol
            for symbol in active_symbols:
                await self.reconciliation.reconcile_symbol(symbol)

            self.logger.info("✅ Global sweep complete")

        except Exception as e:
            self.logger.error(f"❌ Global sweep failed: {e}")

    async def emergency_sweep(
        self,
        symbols: Optional[List[str]] = None,
        close_positions: bool = False,
        reason: str = "MANUAL",
        watchdog: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Emergency sweep: Clean up state (Cancel Orders + Optional Close Positions).

        Used on startup (safe mode) and shutdown (optional close).
        Cancels orders FIRST, then closes positions if requested.

        Args:
            symbols: List of symbols to sweep. If None, detects from exchange.
            close_positions: Whether to force close all open positions.
            reason: Reason for closing positions (e.g., "TIMEOUT", "SHUTDOWN").
            watchdog: Optional watchdog to signal progress via heartbeats.

        Returns:
            Report with positions closed and orders cancelled
        """
        self.logger.info(f"🧹 EMERGENCY SWEEP: Cancelling orders {'& Closing Positions' if close_positions else ''}...")

        report = {
            "positions_closed": 0,
            "orders_cancelled": 0,
            "symbols_processed": [],
            "errors": [],
        }

        # Phase 29: Enable Shutdown Mode to bypass circuit breakers for graceful exit
        self.error_handler.set_shutdown_mode(True)

        if not self.adapter:
            self.logger.warning("⚠️ Exchange adapter not initialized in Croupier, skipping sweep")
            return report

        try:
            # STEP 0: Gracefully close TRACKED positions first (Counts towards stats/PnL)
            if close_positions and self.position_tracker.open_positions:
                tracked_positions = list(self.position_tracker.open_positions)
                self.logger.info(f"🛡️ Gracefully closing {len(tracked_positions)} tracked positions (Parallel)...")

                # Use Semaphore to avoid overwhelming the exchange API
                # Slightly increased for shutdown efficiency now that breakers are bypassed
                semaphore = asyncio.Semaphore(10)

                async def close_with_semaphore(pos):
                    async with semaphore:
                        # Only close positions for the requested symbols (or all if symbols=None)
                        if symbols and pos.symbol not in symbols:
                            return

                        try:
                            self.logger.info(f"📉 Closing tracked position {pos.trade_id} ({pos.symbol}) via Manager")
                            # Pass position object directly to avoid ID collision races
                            await self.close_position(pos.trade_id, exit_reason=reason, position_obj=pos)
                            report["positions_closed"] += 1
                            if watchdog:
                                watchdog.heartbeat()  # Signal progress
                        except (asyncio.CancelledError, Exception, BaseException) as e:
                            self.logger.error(f"❌ Failed to gracefully close {pos.trade_id}: {type(e).__name__} | {e}")

                # Launch closures in parallel with protected result gathering
                await asyncio.gather(*(close_with_semaphore(p) for p in tracked_positions), return_exceptions=True)

            # --- OPTIMIZED BRUTE FORCE SWEEP (Catch ghosts/orphans/remainders) ---

            # --- OPTIMIZED BRUTE FORCE SWEEP (Catch ghosts/orphans/remainders) ---
            # We use a loop for the "Smart Exit" to ensure everything is really closed.
            for attempt in range(3):
                self.logger.info(f"🔍 Audit Sweep (Attempt {attempt+1}/3)...")

                # 1. Fetch EVERYTHING once
                all_exchange_positions, all_exchange_orders = await asyncio.gather(
                    self.adapter.fetch_positions(), self.adapter.fetch_open_orders(None), return_exceptions=True
                )

                # Handle potential exceptions in bulk fetch
                if isinstance(all_exchange_positions, Exception):
                    self.logger.error(f"❌ Failed to bulk fetch positions: {all_exchange_positions}")
                    all_exchange_positions = []
                if isinstance(all_exchange_orders, Exception):
                    self.logger.error(f"❌ Failed to bulk fetch orders: {all_exchange_orders}")
                    all_exchange_orders = []

                # 2. Build map of symbol -> state
                symbol_map = {}
                for pos in all_exchange_positions:
                    sym = pos["symbol"]
                    if symbols and sym not in symbols:
                        continue
                    if sym not in symbol_map:
                        symbol_map[sym] = {"positions": [], "orders": []}
                    symbol_map[sym]["positions"].append(pos)

                for order in all_exchange_orders:
                    sym = order["symbol"]
                    if symbols and sym not in symbols:
                        continue
                    if sym not in symbol_map:
                        symbol_map[sym] = {"positions": [], "orders": []}
                    symbol_map[sym]["orders"].append(order)

                if not symbol_map:
                    self.logger.info("✅ Exchange is clean.")
                    break

                self.logger.info(f"🔍 Parallel sweeping {len(symbol_map)} symbols: {list(symbol_map.keys())}")

                # 3. Define the cleanup worker for a single symbol
                async def cleanup_symbol(sym, state):
                    try:
                        # Step A: Cancel all orders (Bulk if available)
                        if state["orders"]:
                            try:
                                await self.adapter.cancel_all_orders(sym)
                                report["orders_cancelled"] += len(state["orders"])
                            except Exception as e:
                                self.logger.warning(
                                    f"⚠️ Bulk cancel failed for {sym}, fallback logic will handle it: {e}"
                                )

                        # Step B: Close all positions
                        if close_positions:
                            for pos in state["positions"]:
                                size = abs(
                                    float(pos.get("contracts", 0) or pos.get("size", 0) or pos.get("amount", 0) or 0)
                                )
                                if size > 0:
                                    side = pos.get("side", "").lower()
                                    close_side = "sell" if side == "long" else "buy"
                                    try:
                                        res = await self.adapter.create_market_order(
                                            symbol=sym, side=close_side, amount=size, params={"reduceOnly": True}
                                        )
                                        self.logger.info(
                                            f"✅ Closed remainder position: {sym} {side} {size} ({reason})"
                                        )

                                        # PERFECT ACCOUNTING: Record this external closure
                                        try:
                                            # We might not know the exact entry price for a ghost,
                                            # so we use 0.0 or the current price as a placeholder
                                            # unless we find it in the tracker's history or exchange info.
                                            fill_price = float(res.get("average") or res.get("price") or 0.0)
                                            if fill_price <= 0:
                                                fill_price = await self.adapter.get_current_price(sym)

                                            # Try to find entry price from exchange info (some connectors provide it)
                                            raw_entry = float(
                                                pos.get("entryPrice") or pos.get("entry_price") or fill_price
                                            )

                                            # PHASE 28: FETCH REAL FEES FOR SWEEP
                                            # During shutdown, we want accuracy but speed.
                                            # We will try to fetch the trade to get the exact Fee.
                                            real_fee = 0.0
                                            try:
                                                # Small pause to allow fill indexing
                                                await asyncio.sleep(0.5)
                                                trades = await self.adapter.fetch_my_trades(sym, limit=3)
                                                # Simple match: last trade for this symbol
                                                if trades:
                                                    # Sort by time just in case
                                                    trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                                                    # Get the most recent trade (our closure)
                                                    latest = trades[0]
                                                    real_fee = float(latest.get("fee", {}).get("cost", 0) or 0)
                                                    # Update price if available
                                                    fill_price = float(latest.get("price", 0) or fill_price)

                                            except Exception as fetch_e:
                                                self.logger.warning(f"⚠️ Could not fetch sweep fee for {sym}: {fetch_e}")

                                            historian.record_external_closure(
                                                symbol=sym,
                                                side=side.upper(),
                                                qty=size,
                                                entry_price=raw_entry,
                                                exit_price=fill_price,
                                                fee=real_fee,  # Real Fee!
                                                reason=f"BRUTE_{reason}",
                                                session_id=self.position_tracker.session_id,
                                            )
                                        except Exception as hist_e:
                                            self.logger.error(f"❌ Failed to record external closure: {hist_e}")

                                        report["positions_closed"] += 1
                                    except Exception as e:
                                        self.logger.error(f"❌ Failed to close remainder {sym}: {e}")

                        if sym not in report["symbols_processed"]:
                            report["symbols_processed"].append(sym)
                    except Exception as e:
                        self.logger.error(f"❌ Error in cleanup worker for {sym}: {e}")

                # 4. Run all cleanup workers in parallel with rate limiting
                semaphore_brute = asyncio.Semaphore(5)

                async def cleanup_with_semaphore(sym, state):
                    async with semaphore_brute:
                        await cleanup_symbol(sym, state)
                        if watchdog:
                            watchdog.heartbeat()

                await asyncio.gather(*(cleanup_with_semaphore(s, st) for s, st in symbol_map.items()))

                if not close_positions:
                    # If we only wanted to cancel orders, one pass is usually enough
                    break

                # Small delay before verification loop if needed
                if attempt < 2:
                    await asyncio.sleep(1)

            self.logger.info(
                f"✅ Emergency sweep complete: "
                f"{report['positions_closed']} positions closed, "
                f"{report['orders_cancelled']} orders cancelled"
            )

            # Reverting: Only clear if we actually closed something on exchange.
            # The ghost position issue must be handled by proper reconciliation, not here.
            if report["positions_closed"] > 0 or report["orders_cancelled"] > 0:
                self.position_tracker.open_positions.clear()
                self.logger.warning(
                    f"⚠️ Cleaned up {report['positions_closed']} positions and "
                    f"{report['orders_cancelled']} orders from exchange"
                )

        except Exception as e:
            self.logger.error(f"❌ Emergency sweep failed: {e}")
            report["errors"].append(str(e))

        finally:
            # Always ensure shutdown mode is disabled after cleanup
            self.error_handler.set_shutdown_mode(False)

        return report
