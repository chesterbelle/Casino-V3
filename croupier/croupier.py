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
import uuid
from typing import Any, Dict, List, Optional

from config import trading as trading_config
from core.error_handling import get_error_handler
from core.interfaces import TimeIterator
from core.observability.decision_auditor import DecisionAuditor
from core.observability.historian import historian

# Phase 31: OrderTracker removed - PositionTracker is now the single source of truth
from core.portfolio.balance_manager import BalanceManager
from core.portfolio.portfolio_guard import GuardConfig, GuardState, PortfolioGuard
from core.portfolio.position_tracker import OpenPosition, PositionTracker
from utils.symbol_norm import normalize_symbol

from .components.drift_auditor import DriftAuditor
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
            "tp_price": 50500.0,
            "sl_price": 49500.0
        })
    """

    # Phase 240: Shutdown Performance
    EXCHANGE_SHUTDOWN_TIMEOUT = 10.0

    def __init__(self, exchange_adapter, initial_balance: float):
        """
        Initialize Croupier orchestrator.

        Args:
            exchange_adapter: ExchangeAdapter for order execution
            initial_balance: Starting capital
        """
        super().__init__()
        self.adapter = exchange_adapter
        # Backward compatibility: some components expect exchange_adapter
        self.exchange_adapter = exchange_adapter
        self.logger = logging.getLogger("Croupier")
        self.session_id = f"sess_{uuid.uuid4().hex[:8]}"

        # Initialize core components
        self.error_handler = get_error_handler()
        self.balance_manager = BalanceManager(initial_balance)
        self.position_tracker = PositionTracker(adapter=exchange_adapter, session_id=self.session_id)

        # Phase 31: PositionTracker is now the single source of truth for order state
        # Initialize specialized components
        self.order_executor = OrderExecutor(
            exchange_adapter, self.error_handler, position_tracker=self.position_tracker
        )
        self.oco_manager = OCOManager(self.order_executor, self.position_tracker, exchange_adapter)

        # Legacy: Still keep reconciliation for Adopt/Cleanup logic, but without its own loop
        self.reconciliation = ReconciliationService(
            exchange_adapter, self.position_tracker, self.oco_manager, croupier=self
        )

        self.exit_manager = ExitManager(self)

        # Phase 103: Forensic Traceability
        self.auditor = DecisionAuditor()

        self.drift_auditor = DriftAuditor(
            exchange_adapter, self.position_tracker, self.reconciliation, self.balance_manager
        )

        self.process_start_balance: float = 0.0
        self.is_drain_mode: bool = False
        self.is_shutting_down: bool = False
        self._drain_in_progress: bool = False  # Task guard for drain status updates
        self._last_funding_sync: float = 0.0  # Phase 30: For precision accounting

        self.logger.info(f"[CORE] ✅ Croupier V4 initialized | Balance: {initial_balance} | Global limit: UNLIMITED")

        # Register callback for automatic cleanup when exchange hits TP/SL
        self.position_tracker.on_close_callback = self._on_position_closed_cleanup

        # Phase 78.2: Connect Liquidation Sheriff (Account Updates)
        # PositionTracker must listen to ACCOUNT_UPDATE to catch external liquidations
        self.adapter.set_account_update_callback(self.position_tracker.handle_account_update)

        # Phase 79.1: Connect Order Updates (Total Visibility)
        # PositionTracker must listen to ORDER_TRADE_UPDATE to catch real-time fills
        # OCOManager must also listen to resolve futures immediately (Phase 91.2 Fix)
        def _on_order_update_wrapper(data: Dict):
            # 1. Update PositionTracker (Primary)
            self.position_tracker.handle_order_update(data)
            # 2. Update OCOManager (Secondary - for bracket fill confirmation)
            asyncio.create_task(self.oco_manager.on_order_update(data))

        self.adapter.set_order_update_callback(_on_order_update_wrapper)

        # Debounce for reconciliations
        self._reconciliation_tasks: Dict[str, float] = {}
        self._reconcile_lock = asyncio.Lock()

        # Phase 4: ReconciliationWorker IPC Queue (set externally by main.py)
        self._recon_queue = None

        # Track pending closures to prevent premature shutdown before PnL is recorded
        self._pending_closures: set = set()

        # Phase 249: PortfolioGuard (Event-Driven Risk Monitor)
        self._kill_switch_triggered: bool = False
        guard_cfg = GuardConfig(
            enabled=getattr(trading_config, "PORTFOLIO_GUARD_ENABLED", True),
            caution_drawdown_pct=getattr(trading_config, "GUARD_CAUTION_DRAWDOWN_PCT", 0.05),
            critical_drawdown_pct=getattr(trading_config, "GUARD_CRITICAL_DRAWDOWN_PCT", 0.10),
            drawdown_window_minutes=getattr(trading_config, "GUARD_DRAWDOWN_WINDOW_MINUTES", 30),
            max_consecutive_losses=getattr(trading_config, "GUARD_MAX_CONSECUTIVE_LOSSES", 5),
            max_errors_in_window=getattr(trading_config, "GUARD_MAX_ERRORS_WINDOW", 10),
            error_window_minutes=getattr(trading_config, "GUARD_ERROR_WINDOW_MINUTES", 5),
            solvency_multiplier=getattr(trading_config, "GUARD_SOLVENCY_MULTIPLIER", 1.25),
            caution_sizing_violations=getattr(trading_config, "GUARD_CAUTION_SIZING_VIOLATIONS", 3),
            terminal_sizing_violations=getattr(trading_config, "GUARD_TERMINAL_SIZING_VIOLATIONS", 10),
            recovery_cooldown_seconds=getattr(trading_config, "GUARD_RECOVERY_COOLDOWN_SECONDS", 300),
        )
        self.portfolio_guard = PortfolioGuard(guard_cfg)
        self.portfolio_guard.add_state_listener(self._on_guard_state_change)

        # Wire guard into BalanceManager and ErrorHandler
        self.balance_manager._portfolio_guard = self.portfolio_guard
        self.error_handler._portfolio_guard = self.portfolio_guard

        # Wire trade close events to guard (via PositionTracker listener)
        self.position_tracker.add_close_listener(self._on_trade_close_guard)

        # Phase 249.1: Trigger initial solvency check (Startup Sanity)
        if initial_balance > 0:
            self.portfolio_guard.on_balance_update(initial_balance)

    @property
    def is_settled(self) -> bool:
        """
        Returns True if the Croupier is fully settled (safe to shutdown).
        1. No open positions in tracker.
        2. No pending close operations waiting for confirmation.
        """
        active_positions = len(self.position_tracker.open_positions)
        pending_closes = len(self._pending_closures)

        is_settled = (active_positions == 0) and (pending_closes == 0)

        if not is_settled:
            self.logger.debug(f"⏳ Croupier Settlement: Pos={active_positions}, PendingCloses={pending_closes}")

        return is_settled

    def set_drain_mode(self, enabled: bool):
        """Enable or disable drain mode (no new entries, narrow exits)."""
        self.is_drain_mode = enabled

        # Bypass circuit breakers during draining to ensure exit attempts continue
        self.error_handler.set_shutdown_mode(enabled)

        if enabled:
            self.logger.warning("[CORE] 🕒 Croupier entering DRAIN MODE. Narrowing TPs for all positions.")

    def set_shutting_down(self, enabled: bool):
        """Enable or disable absolute shutdown mode."""
        self.is_shutting_down = enabled
        if enabled:
            self.logger.warning("🏁 Croupier: SHUTDOWN SIGNAL RECEIVED. Severing non-sweep activities.")

    # =========================================================
    # PHASE 249: PORTFOLIO GUARD INTEGRATION
    # =========================================================

    def _on_guard_state_change(self, old_state: GuardState, new_state: GuardState, reason: str):
        """Handle graduated response from PortfolioGuard."""
        if new_state == GuardState.CAUTION:
            self.logger.warning(f"🛡️ PORTFOLIO GUARD → CAUTION: {reason}. " "New entries blocked.")
        elif new_state == GuardState.CRITICAL:
            self.logger.critical(f"🚨 PORTFOLIO GUARD → CRITICAL: {reason}. " "Activating drain mode.")
            if not self.is_drain_mode:
                self.set_drain_mode(True)
        elif new_state == GuardState.TERMINAL:
            self.logger.critical(f"💀 PORTFOLIO GUARD → TERMINAL: {reason}. " "Emergency shutdown initiated.")
            if not self.is_drain_mode:
                self.set_drain_mode(True)
            self._kill_switch_triggered = True
        elif new_state == GuardState.HEALTHY:
            self.logger.info(f"✅ PORTFOLIO GUARD → HEALTHY: {reason}. " "Normal operation resumed.")
            if self.is_drain_mode:
                self.set_drain_mode(False)

    def _on_trade_close_guard(self, trade_id: str, result: dict):
        """Forward trade close events to PortfolioGuard for loss streak tracking."""
        pnl = result.get("pnl", 0.0)
        exit_reason = result.get("exit_reason", "UNKNOWN")
        self.portfolio_guard.on_trade_closed(pnl, exit_reason)

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
                # Tag position with phase for reporting
                pos.lifecycle_phase = f"DRAIN_{phase}"
                try:
                    await asyncio.wait_for(
                        self.exit_manager.apply_dynamic_exit(pos, phase),
                        timeout=15.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.warning(f"⏰ Drain {phase} timeout for {pos.trade_id} ({pos.symbol}) — skipping")

        tasks = [_apply_with_limit(pos) for pos in active_positions]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def update_drain_status(self, remaining_minutes: float):
        """
        Periodically called during drain phase to trigger progressive exits.

        Schedule (T-45m window):
        - T-45m to T-20m (25m): DEFENSIVE (Break Even) - Extended for PnL protection
        - T-20m to T-10m (10m): AGGRESSIVE (Small Loss / Tight Stops)
        - T-10m to T-5m  (5m):  PANIC (Market Close)
        - T-5m  to T-0m  (5m):  FINAL SWEEP (Already passed to Emergency)
        """
        if self.is_shutting_down:
            return  # Phase 244: Sever non-sweep loops during teardown
        if not self.is_drain_mode or self._drain_in_progress:
            return

        try:
            self._drain_in_progress = True

            # Determine Phase based on window ratio
            # Assuming DRAIN_PHASE_MINUTES = 45
            # T-45 -> Ratio 1.0
            # T-20 -> Ratio 0.44

            # If remaining > 20m: DEFENSIVE (The massive defensive block)
            if remaining_minutes > 20.0:
                phase = "DEFENSIVE"
            # If remaining > 10m: AGGRESSIVE
            elif remaining_minutes > 10.0:
                phase = "AGGRESSIVE"
            # Last 10m: PANIC
            else:
                phase = "PANIC"

            # Apply Phase logic
            await self._apply_drain_phase(phase)

        except Exception as e:
            self.logger.error(f"❌ Error in update_drain_status: {e}")
        finally:
            self._drain_in_progress = False

    # ... (rest of methods) ...

    async def emergency_sweep(
        self,
        symbols: Optional[List[str]] = None,
        close_positions: bool = False,
        reason: str = "MANUAL",
        watchdog: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Emergency sweep: Clean up state (Cancel Orders + Optional Close Positions).
        Includes Rate Limiting to prevent API Saturation (-1021 Errors).
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

                # Phase 200: Concurrent Draining Optimization
                # Phase 236: Reduced from Sem(5) to Sem(3) to prevent API flood during shutdown
                # Each close = 2 cancel requests (TP+SL) + 1 market order = 3 REST calls
                # Sem(3) * 3 calls = max 9 concurrent REST requests (safe for testnet)
                sem = asyncio.Semaphore(3)

                async def close_with_sem(pos, idx, total):
                    async with sem:
                        try:
                            self.logger.info(
                                f"📉 Closing tracked position {pos.trade_id} ({pos.symbol}) [{idx+1}/{total}]"
                            )
                            await self.close_position(
                                pos.trade_id, exit_reason=reason, position_obj=pos, watchdog=watchdog
                            )
                            report["positions_closed"] += 1
                        except Exception as e:
                            self.logger.error(f"❌ Failed to close {pos.trade_id}: {e}")
                        finally:
                            if watchdog:
                                watchdog.heartbeat()
                            # Phase 236: Increased stagger from 50ms to 200ms to prevent API saturation
                            await asyncio.sleep(0.2)

                # Launch all close tasks
                tasks = [close_with_sem(pos, i, len(tracked_positions)) for i, pos in enumerate(tracked_positions)]

                # Filter by symbol if requested
                if symbols:
                    norm_symbols = [normalize_symbol(s) for s in symbols]
                    tasks = [t for t, p in zip(tasks, tracked_positions) if normalize_symbol(p.symbol) in norm_symbols]

                if tasks:
                    await asyncio.gather(*tasks)

            # --- OPTIMIZED BRUTE FORCE SWEEP (Catch ghosts/orphans/remainders) ---
            # We use a loop for the "Smart Exit" to ensure everything is really closed.
            for attempt in range(3):
                self.logger.info(f"🔍 Audit Sweep (Attempt {attempt+1}/3)...")

                if watchdog:
                    watchdog.heartbeat("emergency_sweep", "Bulk fetch start")

                # 1. Fetch EVERYTHING once
                # Phase 240: Use strict timeout for audit fetch
                try:
                    all_exchange_positions, all_exchange_orders = await asyncio.wait_for(
                        asyncio.gather(
                            self.adapter.fetch_positions(), self.adapter.fetch_open_orders(None), return_exceptions=True
                        ),
                        timeout=self.EXCHANGE_SHUTDOWN_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    self.logger.error("❌ Bulk fetch timed out during emergency_sweep")
                    all_exchange_positions, all_exchange_orders = [], []

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

                for i, order in enumerate(all_exchange_orders):
                    if watchdog and i % 5 == 0:
                        watchdog.heartbeat("emergency_sweep", f"Processing order {i}/{len(all_exchange_orders)}")
                    sym = normalize_symbol(order["symbol"])
                    if symbols:
                        norm_symbols = [normalize_symbol(s) for s in symbols]
                        if sym not in norm_symbols:
                            continue
                    if sym not in symbol_map:
                        symbol_map[sym] = {"positions": [], "orders": []}
                    symbol_map[sym]["orders"].append(order)

                if not symbol_map:
                    self.logger.info("✅ Exchange is clean.")
                    break

                self.logger.info(f"🔍 Sweeping {len(symbol_map)} symbols sequentially...")

                # 3. Sequential Processing (Phase 33 Fix)
                for sym, state in symbol_map.items():
                    if watchdog:
                        watchdog.heartbeat()

                    try:
                        # Step A: Cancel all orders
                        if state["orders"]:
                            await self.adapter.cancel_all_orders(sym, timeout=self.EXCHANGE_SHUTDOWN_TIMEOUT)
                            report["orders_cancelled"] += len(state["orders"])
                            await asyncio.sleep(0.1)  # Tiny pause

                        # Step B: Close positions
                        if close_positions and state["positions"]:
                            for i, pos in enumerate(state["positions"]):
                                if watchdog:
                                    watchdog.heartbeat(
                                        "emergency_sweep", f"Closing {sym} {i+1}/{len(state['positions'])}"
                                    )
                                size = abs(
                                    float(pos.get("contracts", 0) or pos.get("size", 0) or pos.get("amount", 0) or 0)
                                )
                                if size > 0:
                                    side = pos.get("side", "").lower()
                                    close_side = "sell" if side == "long" else "buy"

                                    # Create Market Order
                                    await self.adapter.create_market_order(
                                        symbol=sym,
                                        side=close_side,
                                        amount=size,
                                        params={"reduceOnly": True, "timeout": self.EXCHANGE_SHUTDOWN_TIMEOUT},
                                    )
                                    self.logger.info(f"✅ Closed remainder: {sym} {size}")

                                    # Record Closure (Phase 87: Zero-Leakage)
                                    try:
                                        # Estimate PnL (Neutral) or fetch current price
                                        exit_price = 0.0
                                        try:
                                            # Phase 240: Fast Ticker with timeout
                                            ticker = await asyncio.wait_for(self.adapter.fetch_ticker(sym), timeout=5.0)
                                            exit_price = float(ticker.get("last", 0))
                                        except Exception:
                                            pass

                                        # Record in Historian so variance is explained
                                        historian.record_trade(
                                            {
                                                "trade_id": f"AUDIT_{int(time.time()*1000)}",
                                                "symbol": sym,
                                                "side": "SHORT" if close_side == "sell" else "LONG",
                                                "action": "CLOSE",
                                                "amount": size,
                                                "price": exit_price,
                                                "pnl": 0.0,  # Will be adjusted by Ledger Reconciler later
                                                "fee": 0.0,
                                                "exit_reason": "AUDIT_SWEEP_CLOSE",
                                                "session_id": self.session_id,
                                            }
                                        )
                                    except Exception as hist_err:
                                        self.logger.error(f"⚠️ Failed to record audit closure for {sym}: {hist_err}")

                                    report["positions_closed"] += 1
                                    await asyncio.sleep(0.2)  # Throttle closures

                    except Exception as e:
                        self.logger.error(f"❌ Error sweeping {sym}: {e}")

                if not close_positions:
                    break

                await asyncio.sleep(1)

            # ... (Rest of method) ...
            self.logger.info(
                f"✅ Emergency sweep complete: "
                f"{report['positions_closed']} positions closed, "
                f"{report['orders_cancelled']} orders cancelled"
            )

            # Reverting: Only clear if we actually closed something on exchange.
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
            self.error_handler.set_shutdown_mode(False)

        return report

    async def modify_tp(
        self,
        trade_id: str,
        new_tp_price: float,
        symbol: str,
        old_tp_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Modify Take Profit for a position using the unified OCOManager."""
        # Centralized Governance: Check if position is available for modification
        position = self.position_tracker.get_position(trade_id)
        if position and position.status == "CLOSING":
            self.logger.debug(f"⏭️ Skipping modify_tp: Position {trade_id} is already CLOSING")
            return {"status": "skipped", "reason": "position_closing"}

        symbol = normalize_symbol(symbol)
        self.logger.info(f"🔄 Modifying TP for {trade_id} | New TP: {new_tp_price:.2f}")

        try:
            result = await self.oco_manager.modify_bracket(
                trade_id=trade_id, symbol=symbol, new_tp_price=new_tp_price, timeout=trading_config.GRACEFUL_TP_TIMEOUT
            )

            if result.get("status") == "success":
                if "tp_id" in result:
                    # Reconciliation for manual fallback safety (Debounced)
                    self.trigger_reconciliation_task(symbol)

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

        # DRAIN/SHUTDOWN MODE CHECK
        if self.is_shutting_down:
            self.logger.debug(f"⏭️ Skipping execute_order: SHUTDOWN active for {symbol}")
            return {"status": "error", "message": "Shutdown active"}

        if self.is_drain_mode:
            self.logger.warning(f"🚫 Drain Mode Active: Rejecting new entry for {symbol}")
            return {"status": "error", "message": "Drain mode active"}

        # Phase 248: Cooldown check to prevent HFT Execution Loops
        if self.position_tracker.is_symbol_blocked(symbol):
            self.logger.warning(f"🛡️ Signal Cooldown Active for {symbol}: Rejecting execution.")
            return {"status": "error", "message": "Signal cooldown active"}

        # 1. Execute OCO bracket order
        self.logger.info(f"📥 Execute order request: {order['side']} {order['symbol']}")

        # Extract contributors (sensor IDs) for tracking
        contributors = order.get("contributors", [])

        # Phase 42: Master Sizing enforced. Amount must be provided by OrderManager.
        # We no longer calculate sizing here to avoid "Esquizofrenia Numérica" (Dual Rounding).
        if "amount" not in order or float(order.get("amount", 0)) <= 0:
            raise ValueError("Order missing 'amount'. Sizing must be handled by OrderManager.")

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

        # Use safe get for fill_price as optimistic OCOs won't have it yet
        entry_p = result.get("fill_price") or getattr(position, "entry_price", 0)
        self.logger.info(f"✅ Position opened: {position.trade_id} | Entry: {entry_p:.2f}")

        return result

    async def close_position(
        self,
        trade_id: str,
        exit_reason: str = "MANUAL",
        position_obj: Optional[Any] = None,
        watchdog: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Close a position manually.

        1. Cancel TP/SL orders
        2. Execute market close order
        """
        # Centralized Governance: Attempt to lock position for closure
        # This replaces the manual status check with an atomic architectural guard
        if not await self.position_tracker.lock_for_closure(trade_id):
            self.logger.debug(f"⏭️ Skipping close_position: {trade_id} is busy or already CLOSING")
            return {"status": "skipped", "reason": "already_closing"}

        # Phase 84: Track pending closure for Settlement
        self._pending_closures.add(trade_id)

        # At this point, the position status is "CLOSING" and we hold the governance lock
        # We RE-FETCH position to ensure we have the locked object
        position = self.position_tracker.get_position(trade_id)
        if not position:
            self.position_tracker.unlock(trade_id)  # Safety
            self._pending_closures.discard(trade_id)
            raise ValueError(f"Position vanished after locking: {trade_id}")

        self.logger.info(f"📤 Closing position: {trade_id} | {position.symbol} {position.side}")

        try:
            # 1. Cancel TP/SL
            try:
                await self.oco_manager.cancel_bracket(position.tp_order_id, position.sl_order_id, position.symbol)
            except Exception as ce:
                self.logger.warning(
                    f"⚠️ Non-critical failure cancelling bracket for {trade_id}: {ce}. Proceeding to close market position."
                )

            if watchdog:
                watchdog.heartbeat("close_position", f"Bracket cancelled for {position.symbol}")

            # 2. Execute market close

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

            try:
                # Phase 43: Universal Funnel - Delegate "Smart Close" to OrderExecutor
                result = await self.order_executor.force_close_position(
                    symbol=position.symbol, side=position.side, amount=amount
                )
            except Exception as e:
                # Phase 82: Handle position already closed by TP/SL gracefully
                from core.exceptions import PositionAlreadyClosedError

                if isinstance(e, PositionAlreadyClosedError):
                    self.logger.info(
                        f"✅ Position {trade_id} was already closed (TP/SL hit). Confirming closure in tracker."
                    )
                    # Get current price for PnL estimation
                    try:
                        exit_price = await asyncio.wait_for(
                            self.adapter.get_current_price(position.symbol), timeout=5.0
                        )
                    except Exception:
                        exit_price = position.entry_price  # Neutral fallback

                    # Calculate approximate PnL
                    if position.entry_price > 0:
                        if position.side == "LONG":
                            pnl = (exit_price - position.entry_price) * position.notional / position.entry_price
                        else:
                            pnl = (position.entry_price - exit_price) * position.notional / position.entry_price
                    else:
                        pnl = 0.0

                    self.position_tracker.confirm_close(
                        trade_id=trade_id,
                        exit_price=exit_price,
                        exit_reason="TP_SL_HIT",
                        pnl=pnl,
                        fee=0.0,
                    )
                    return {"status": "already_closed", "exit_price": exit_price, "pnl": pnl}
                else:
                    self.logger.error(f"❌ Smart Close Failed for {trade_id}: {e}. Triggering RAW EMERGENCY BYPASS.")
                    # Extreme Failsafe: Bypass OrderExecutor and Circuit Breakers entirely
                    connector = getattr(self.adapter, "connector", None) or getattr(self.adapter, "_connector", None)
                    if connector:
                        close_side = "sell" if position.side == "LONG" else "buy"
                        try:
                            result = await connector.create_order(
                                symbol=position.symbol,
                                side=close_side,
                                amount=amount,
                                order_type="market",
                                params={"reduceOnly": True},
                                timeout=5.0,  # CRITICAL: Prevent 5-minute aiohttp fallback hang
                            )
                            self.logger.warning(f"🛡️ RAW EMERGENCY BYPASS SUCCESS for {position.symbol}")
                        except Exception as bypass_err:
                            if "-2022" in str(bypass_err) or "ReduceOnly" in str(bypass_err):
                                self.logger.info(
                                    f"✅ Position {trade_id} was actually already closed. Handled gracefully."
                                )
                                try:
                                    exit_price = await asyncio.wait_for(
                                        self.adapter.get_current_price(position.symbol), timeout=5.0
                                    )
                                except Exception:
                                    exit_price = position.entry_price

                                if position.entry_price > 0:
                                    if position.side == "LONG":
                                        pnl = (
                                            (exit_price - position.entry_price)
                                            * position.notional
                                            / position.entry_price
                                        )
                                    else:
                                        pnl = (
                                            (position.entry_price - exit_price)
                                            * position.notional
                                            / position.entry_price
                                        )
                                else:
                                    pnl = 0.0

                                self.position_tracker.confirm_close(
                                    trade_id=trade_id, exit_price=exit_price, exit_reason="TP_SL_HIT", pnl=pnl, fee=0.0
                                )
                                return {"status": "already_closed", "exit_price": exit_price, "pnl": pnl}

                            self.logger.critical(f"🔥 RAW EMERGENCY BYPASS FAILED. POSITION ORPHANED: {bypass_err}")
                            return {"status": "error", "message": str(bypass_err), "original_error": str(e)}
                    else:
                        self.logger.critical("🔥 RAW EMERGENCY BYPASS FAILED. No connector available.")
                        return {"status": "error", "message": "No connector", "original_error": str(e)}

            fill_price = float(result.get("average", 0) or result.get("price", 0))

            # FIX: Prevent 0.0 fill price from destroying PnL
            if fill_price <= 0:
                self.logger.warning(
                    f"⚠️ Order result missing fill price (Got {fill_price}). Fetching current price for PnL estimation..."
                )
                try:
                    fill_price = await asyncio.wait_for(self.adapter.get_current_price(position.symbol), timeout=5.0)
                    self.logger.info(f"✅ Fetched fallback price: {fill_price}")
                except Exception as e:
                    self.logger.error(f"❌ Failed to fetch current price for fallback: {e}")
                    # Fallback to entry price to avoid massive PnL spike (neutral exit)
                    fill_price = position.entry_price

            self.logger.info(f"✅ Position closed: {trade_id} | Fill: {fill_price}")

            # The lock is released by confirm_close or in the finally block below
            # if confirm_close is not called.

            # Calculate PnL
            if position.entry_price > 0:
                if position.side == "LONG":
                    pnl = (fill_price - position.entry_price) * position.notional / position.entry_price
                else:
                    pnl = (position.entry_price - fill_price) * position.notional / position.entry_price
            else:
                pnl = 0.0

            # PHASE 35: DEFERRED FORENSIC ENRICHMENT (No-Lag)
            # We record immediately with 0 fee, then enrich in background to avoid blocking execution.

            asyncio.create_task(self._deferred_fee_enrichment(trade_id, position.symbol))

            self.position_tracker.confirm_close(
                trade_id=trade_id,
                exit_price=fill_price,
                exit_reason=exit_reason,
                pnl=pnl,
                fee=0.0,  # Initially 0, will be updated by background task
            )

            # IMPORTANT: Position is now removed from tracker, lock is effectively gone.

            return result
        finally:
            # Phase 236: Mark as CLOSE_FAILED instead of reverting to ACTIVE
            # Reverting to ACTIVE causes infinite retry loops during drain/shutdown
            # (drain ticker retries → fails → reverts → retries → 587 stalls)
            # CLOSE_FAILED allows emergency_sweep audit to pick it up without drain retries
            if position and getattr(position, "status", "") == "CLOSING":
                self.logger.warning(f"⚠️ Marking {trade_id} as CLOSE_FAILED (will not auto-retry)")
                position.status = "CLOSE_FAILED"

            self.position_tracker.unlock(trade_id, position=position)

    def _on_position_closed_cleanup(self, trade_id: str, result: Dict[str, Any]):
        """
        Callback triggered by PositionTracker when a position is removed.
        Used to cleanup bracket orders if the position was closed by the exchange (TP/SL).
        """
        # Phase 84: Mark closure as settled (PnL recorded)
        self._pending_closures.discard(trade_id)

        # Phase 103: Forensic Traceability
        trace_id = result.get("trace_id")
        if trace_id:
            self.auditor.record_execution(trace_id, result)

        # We start an async task for cleanup to avoid blocking the tracker

        asyncio.create_task(self._async_bracket_cleanup(trade_id, result))

    async def _async_bracket_cleanup(self, trade_id: str, result: Dict[str, Any]):
        """Background task to cancel remaining bracket orders."""
        try:
            symbol = result.get("symbol")
            if symbol:
                self.logger.info(f"🧹 Performing bracket cleanup for {symbol} after close...")
                await self.adapter.cancel_all_orders(symbol)
        except Exception as e:
            self.logger.error(f"❌ Bracket cleanup failed for {trade_id}: {e}")

    async def modify_sl(
        self,
        trade_id: str,
        new_sl_price: float,
        symbol: str,
        old_sl_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Modify Stop Loss for a position using the unified OCOManager."""
        # State Guard: Check status BEFORE any action
        position = self.position_tracker.get_position(trade_id)
        if position and position.status == "CLOSING":
            self.logger.debug(f"⏭️ Skipping modify_sl: Position {trade_id} is CLOSING")
            return {"status": "skipped", "reason": "position_closing"}

        symbol = normalize_symbol(symbol)
        self.logger.info(f"🔄 Modifying SL for {trade_id} | New SL: {new_sl_price:.2f}")

        try:
            result = await self.oco_manager.modify_bracket(
                trade_id=trade_id, symbol=symbol, new_sl_price=new_sl_price, timeout=trading_config.GRACEFUL_SL_TIMEOUT
            )

            if result.get("status") == "success":
                if "sl_id" in result:
                    # Reconciliation as a safety measure for manual fallback (Debounced)
                    self.trigger_reconciliation_task(symbol)

                return {
                    "status": "success",
                    "new_order_id": result.get("native_id") or result.get("sl_id"),
                    "new_sl_price": new_sl_price,
                }
            return result

        except Exception as e:
            self.logger.error(f"❌ Failed to modify SL: {e}")
            raise e

    def trigger_reconciliation_task(self, symbol: str):
        """Spawns a debounced reconciliation task."""
        symbol = normalize_symbol(symbol)
        now = time.time()

        # Debounce: Minimum 5s between reconciliations for the same symbol
        last_run = self._reconciliation_tasks.get(symbol, 0)
        if now - last_run < 5.0:
            self.logger.debug(f"⏭️ Skipping debounced reconciliation for {symbol}")
            return

        self._reconciliation_tasks[symbol] = now
        asyncio.create_task(self.reconcile_positions(symbol))

    def set_recon_queue(self, queue):
        """Phase 4: Attach the ReconciliationWorker's output queue."""
        self._recon_queue = queue
        self.logger.info("✅ ReconciliationWorker queue attached (Phase 4 State Isolation)")

    async def reconcile_positions(self, symbol: Optional[str] = None):
        """
        Reconcile positions with exchange.
        Phase 4: Prefers pre-fetched data from ReconciliationWorker if available.

        Args:
            symbol: Symbol to reconcile (None = all symbols)

        Returns:
            Reconciliation report
        """
        if symbol:
            return await self.reconciliation.reconcile_symbol(symbol)

        # Phase 4: Try to use cached data from the worker queue (Zero REST on main loop)
        if self._recon_queue is not None:
            try:
                payload = self._recon_queue.get_nowait()
                exchange_positions = payload.get("exchange_positions", [])
                open_orders = payload.get("open_orders", [])
                self.logger.debug(f"📡 Using Worker cache: {len(exchange_positions)} pos, {len(open_orders)} orders")
                return await self.reconciliation.reconcile_from_cache(exchange_positions, open_orders)
            except Exception:
                # Queue empty or stale — worker hasn't pushed yet, fall through to legacy
                pass

        # Fallback: Direct REST calls (legacy path)
        return await self.reconciliation.reconcile_all()

    def get_balance(self) -> float:
        """Get current available balance."""
        return self.balance_manager.balance

    def get_equity(self) -> float:
        """Get current equity (balance + unrealized PnL)."""
        return self.balance_manager.equity

    def get_open_positions(self) -> List[OpenPosition]:
        """
        Get all open positions tracked in memory.
        Includes ACTIVE, OPENING, MODIFYING, CLOSING, and OFF_BOARDING states.
        """
        return self.position_tracker.open_positions

    def get_active_positions(self, symbol: Optional[str] = None) -> List[OpenPosition]:
        """
        Phase 234: Get only positions that should block new entries.
        Excludes CLOSING and OFF_BOARDING states.
        """
        return self.position_tracker.get_active_positions(symbol)

    def can_open_position(self, margin_required: float) -> bool:
        """Check if we can open a new position."""
        if self.is_drain_mode:
            return False
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

        try:
            # PHASE 69: Atomic-Style Registration (Memory first, then state/stats)
            # Add to tracker immediately
            self.position_tracker.open_positions.append(position)

            # Update granular counters
            self.position_tracker.total_trades_opened += 1
            if position.side == "LONG":
                self.position_tracker.new_longs += 1
            else:
                self.position_tracker.new_shorts += 1

            # Trigger state save (non-blocking)
            self.position_tracker._trigger_state_change()

        except Exception as e:
            self.logger.error(f"⚠️ Critical failure during position accounting: {e}")
            # We DON'T remove it from open_positions here;
            # better to have a tracked-but-uncounted position than a "Ghost".

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
                try:
                    await self.adapter.cancel_order(order["id"], symbol)
                except Exception as inner_e:
                    # Log but continue to ensure we try to cancel others
                    self.logger.warning(f"⚠️ Failed to cancel individual order {order.get('id')} in cleanup: {inner_e}")

            self.logger.info(f"✅ Cleanup processed {len(open_orders)} open orders for {symbol}")
        except Exception as e:
            self.logger.error(f"❌ Error fetching/cancelling open orders for {symbol}: {e}")

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
        # Phase 102: Industrial Resilience - Start Drift Auditor
        await self.drift_auditor.start()

    async def stop(self) -> None:
        """Stop components."""
        self.logger.info("🛑 Croupier Reactor Stopped")

        # Phase 102: Industrial Resilience - Stop Drift Auditor
        await self.drift_auditor.stop()

    async def tick(self, timestamp: float) -> None:
        """
        Single tick entry point.
        Unifies all periodic activities.
        """
        # Phase 31: OrderTracker removed - PositionTracker handles order state

        # 2. Periodic Balance Sync (Every 5 mins) - Offset by 30s to avoid candle boundary
        if int(timestamp) % 300 == 30:
            self._run_periodic_task(self._sync_balance(), "BalanceSync", timeout=30.0)

        # 2.5. Periodic Funding Sync (Every 10 mins) - Phase 30
        if timestamp - self._last_funding_sync >= 600:
            self._run_periodic_task(self._sync_funding_fees(), "FundingSync", timeout=45.0)

        # 3. Periodic Reconciliation (Every 60s) - Safety Net for Ghosts
        # Phase 180: Offset by 15s to avoid colliding with 42 candle closures at :00
        if int(timestamp) % 60 == 15:
            # We use reconcile_positions(None) to reconcile ALL symbols
            # This is lightweight if tracking matches exchange, heavy if detachment found.
            self._run_periodic_task(self.reconcile_positions(None), "GlobalRecon", timeout=45.0)

        # 3. Dynamic Exits (If needed, can be driven here)
        # Note: In V3, ExitManager was likely driven by external ticks or own loop.
        # In V4, it should be driven here.
        # await self.exit_manager.tick(timestamp)

    def _run_periodic_task(self, coro, name: str, timeout: float):
        """Helper to run a periodic task with strict timeout and pile-up protection."""

        async def _execution_wrapper():
            try:
                await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                self.logger.error(f"⏰ Periodic Task {name} TIMED OUT after {timeout}s")
            except Exception as e:
                self.logger.error(f"❌ Periodic Task {name} FAILED: {e}", exc_info=True)

        asyncio.create_task(_execution_wrapper())

    async def _sync_balance(self):
        """Standardized balance sync."""
        try:
            exchange_balance = await self.adapter.fetch_balance()
            actual_equity = (exchange_balance.get("total") or {}).get("USDT", 0.0)
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

        self._last_funding_sync = now
        try:
            income_list = await self.adapter.fetch_income(income_type="FUNDING_FEE", since=since)

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

    async def reconcile_ledger_with_exchange(self):
        """
        Fetch Income History (Ledger) from exchange and reconcile with local DB.
        Eliminates 'Unexplained Variance' by capturing Funding Fees and Adjustments.
        """
        self.logger.info("🏦 Starting Ledger Reconciliation (Bank Statement Match)...")
        try:
            # Fetch last 24h or last 1000 records
            # start_time = None (Defaults to recent)
            income_history = await self.adapter.fetch_income(income_type=None, limit=1000)

            if income_history:
                # Delegate to Historian (Phase 110: Pass session_start_ts for isolation)
                historian.reconcile_ledger(
                    income_history,
                    session_id=self.position_tracker.session_id,
                    min_timestamp=self.position_tracker.session_start_ts,
                )
                self.logger.info("✅ Ledger Reconciliation Complete.")
            else:
                self.logger.info("ℹ️ No Income History records returned from exchange.")

        except Exception as e:
            self.logger.error(f"❌ Ledger Reconciliation Failed: {e}")

    def set_process_start_balance(self, balance: float):
        """Sets the exact balance at the start of this execution."""
        self.process_start_balance = float(balance)
        self.logger.info(f"[WALLET] 💰 Process Start Balance: {self.process_start_balance:.2f} USDT")

    async def get_session_summary(self, final_balance: Optional[float] = None) -> Dict[str, Any]:
        """
        Get precise trade stats from Historian (Net PnL) and Account Delta.

        Args:
            final_balance: Optional real wallet balance at end of session.
                          If provided, calculates 'Leakage' (untracked pnl).
        """
        self.logger.debug(f"📊 Fetching Session Stats for ID: {self.position_tracker.session_id}")
        stats = await historian.get_session_stats(session_id=self.position_tracker.session_id)

        # Phase 68: Granular Error Reporting
        stats["error_breakdown"] = await historian.get_error_breakdown(session_id=self.position_tracker.session_id)

        # Calculate Transparency Metrics (Phase 30)
        strategy_net_pnl = stats.get("total_net_pnl", 0.0)

        # Robust conversion for final_balance (handle "N/A" or other non-numeric strings)
        try:
            final_bal_float = float(final_balance) if final_balance is not None else None
        except (ValueError, TypeError):
            final_bal_float = None

        if final_bal_float is not None and self.process_start_balance > 0:
            account_delta = final_bal_float - self.process_start_balance
            # Leakage = Actual change - Strategy PnL (from historian)
            # Strategy PnL in stats now includes healed trades (Phase 61)
            # But Total Net PnL is the ground truth sum of all trades in DB
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

    async def _deferred_fee_enrichment(self, trade_id: str, symbol: str, delay_sec: float = 2.0):
        """
        Background task to enrichment fee accounting without blocking main execution.
        Waits for exchange indexing, then updates Historian.
        """
        try:
            await asyncio.sleep(delay_sec)
            trades = await self.adapter.fetch_my_trades(symbol, limit=5)
            if not trades:
                return

            # Sort by timestamp descending
            trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

            # Match criteria: Recent trades for this symbol
            # Since we record with trade_id (bot level), matching exact order ID is safer
            # Local positions often store exit order IDs.
            # For simplicity in this background task, we take the most recent fee if it hasn't been enriched yet.
            real_fee = float((trades[0].get("fee") or {}).get("cost", 0) or 0)

            if real_fee > 0:
                self.logger.info(f"💰 Background Enrichment: Updating trade {trade_id} with exit_fee={real_fee:.4f}")
                historian.update_trade_fee(trade_id, real_fee)

        except Exception as e:
            self.logger.warning(f"⚠️ Background enrichment failed for {trade_id}: {e}")

    # ... rest of the file ...
