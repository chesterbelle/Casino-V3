"""
ReconciliationService - Syncs local state with exchange.

This component is responsible for:
- Periodic reconciliation of positions with exchange
- Detecting and fixing positions without TP/SL
- Handling unknown positions from exchange (Adoption)
- Cleaning up orphaned orders
- Managing Ghost Positions (Local-only removal)

Author: Casino V3 Team
Version: 3.1.0
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.error_handling import RetryConfig, get_error_handler
from core.exceptions import TransientCommunicationError
from core.observability.historian import historian
from core.observability.metrics import (
    resilience_healing_events_total,
    resilience_orphan_cancels_total,
    resilience_orphan_skips_total,
)
from core.portfolio.position_tracker import OpenPosition, PositionTracker
from utils.symbol_norm import normalize_symbol


class ReconciliationService:
    """
    Reconciles local position state with exchange state.

    Handles:
    - Ghosts: Local positions not on exchange → Silent Removal
    - Unknowns: Exchange positions not in tracker → Strict Adoption (if Healthy) or Close
    - Orphans: Orders without valid position → Cancel
    """

    def __init__(self, exchange_adapter, position_tracker: PositionTracker, oco_manager, croupier=None):
        """
        Initialize ReconciliationService.

        Args:
            exchange_adapter: ExchangeAdapter for fetching positions/orders
            position_tracker: PositionTracker instance
            oco_manager: OCOManager for fixing missing TP/SL
            croupier: Croupier instance for background tasks
        """
        self.adapter = exchange_adapter
        self.tracker = position_tracker
        self.oco_manager = oco_manager
        self.croupier = croupier
        self.error_handler = get_error_handler()
        self.logger = logging.getLogger("ReconciliationService")

        # Retry config for reconciliation operations
        self.reconcile_retry_config = RetryConfig(max_retries=3, backoff_base=1.0, backoff_factor=2.0, jitter=True)

    async def reconcile_all(self) -> List[Dict[str, Any]]:
        """
        Reconcile ALL symbols in a single optimized pass.
        Fetches all positions and all orders once from the exchange.
        """
        self.logger.info("[SYNC] 🔄 Starting global reconciliation for all symbols")
        reports = []

        try:
            # 1. Fetch current exchange state
            # Use [] to fetch ALL symbols, bypassing the adapter's single-symbol pin
            exchange_positions = await self._fetch_exchange_positions([])
            if exchange_positions is None:
                self.logger.error("❌ Aborting global reconciliation due to fetch error")
                return []

            open_orders = await self.adapter.fetch_open_orders([])
            self.logger.info(
                f"[SYNC] 🔍 Global sync sees {len(exchange_positions)} positions and {len(open_orders)} orders"
            )

            # Phase 16: Active Verification (Anti-Glitch Safety Valve)
            # If local tracking shows significant activity but exchange reports ZERO, verify hard.
            local_count = self.tracker.get_stats().get("open_positions", 0)
            exchange_count = len(
                [p for p in exchange_positions if float(p.get("contracts", 0) or p.get("size", 0)) != 0]
            )
            GLITCH_THRESHOLD = 5

            if local_count > GLITCH_THRESHOLD and exchange_count == 0:
                self.logger.warning(
                    f"⚠️ Potential Exchange Glitch Detected! Reported 0 positions vs {local_count} local. "
                    "Initiating Active Verification Protocol..."
                )

                # Active Verification Loop
                is_glitch_confirmed = False
                for attempt in range(1, 4):
                    await asyncio.sleep(1.0)
                    self.logger.info(f"🕵️ Verification Attempt {attempt}/3...")
                    retry_positions = await self._fetch_exchange_positions(None)

                    if retry_positions:
                        retry_count = len(
                            [p for p in retry_positions if float(p.get("contracts", 0) or p.get("size", 0)) != 0]
                        )
                        if retry_count > 0:
                            self.logger.info(f"✅ Glitch Resolved! Found {retry_count} positions on attempt {attempt}.")
                            exchange_positions = retry_positions
                            is_glitch_confirmed = True
                            break

                if not is_glitch_confirmed:
                    self.logger.critical(
                        f"🚨 MASS DETACHMENT ALERT: Exchange persistently reports 0 positions vs {local_count} local. "
                        "Aborting reconciliation to prevent mass-close safety hazard."
                    )
                    return []

            # Fetch ALL open orders once
            open_orders = await self.error_handler.execute_with_breaker(
                "reconciliation_fetch", self.adapter.fetch_open_orders, None, retry_config=self.reconcile_retry_config
            )
            if open_orders is None:
                self.logger.error("❌ Aborting global reconciliation due to orders fetch error")
                return []

            # Group exchange positions and orders by symbol for easy access
            from collections import defaultdict

            ex_pos_by_symbol = defaultdict(list)
            for p in exchange_positions:
                ex_pos_by_symbol[normalize_symbol(p["symbol"])].append(p)

            orders_by_symbol = defaultdict(list)
            open_orders_symbols = set()
            for o in open_orders:
                norm_sym = normalize_symbol(o["symbol"])
                orders_by_symbol[norm_sym].append(o)
                open_orders_symbols.add(norm_sym)

            # Discover all symbols to check (Tracker + Exchange + Open Orders)
            # Use unified normalized symbols for all sources
            local_symbols = {normalize_symbol(pos.symbol) for pos in self.tracker.open_positions}
            exchange_symbols = {
                normalize_symbol(p["symbol"]) for p in exchange_positions if abs(float(p.get("contracts", 0))) > 1e-8
            }

            # Phase 102/238/243: Industrial Resilience - Throttled Balance Reconciliation
            # Phase 243: Skip balance sync if rest_account_api CB is not CLOSED
            # This prevents redundant blocking calls that compound the death spiral
            _account_cb_healthy = True
            try:
                account_cb = self.error_handler.get_circuit_breaker("rest_account_api")
                _account_cb_healthy = account_cb.is_closed
            except Exception:
                pass

            if _account_cb_healthy and self.croupier and hasattr(self.croupier, "balance_manager"):
                last_bal_reconcile = getattr(self, "_last_balance_reconcile", 0)
                if (time.time() - last_bal_reconcile) > 300:  # Every 5 minutes
                    try:
                        balance_data = await self.adapter.connector.fetch_balance()
                        new_balance = (balance_data.get("total") or {}).get("USDT", 0.0)
                        if new_balance > 0:
                            self.logger.info(f"[SYNC] 💰 Reconciling balance: {new_balance:.2f} USDT")
                            self.croupier.balance_manager.set_balance(new_balance)
                            self._last_balance_reconcile = time.time()
                    except Exception as e:
                        self.logger.warning(f"⚠️ Failed to reconcile balance: {e}")
            elif not _account_cb_healthy:
                self.logger.debug("⏭️ Skipping balance reconciliation: rest_account_api CB is not CLOSED")

            all_symbols = local_symbols | exchange_symbols | open_orders_symbols

            # PHASE 58: Parallelize reconciliation to prevent loop lag
            semaphore = asyncio.Semaphore(5)  # Max 5 symbols at once to stay safe

            async def sem_reconcile(symbol):
                async with semaphore:
                    return await self._reconcile_symbol_data(
                        symbol,
                        ex_pos_by_symbol[symbol],
                        orders_by_symbol[symbol],
                        mode="active",
                    )

            tasks = [sem_reconcile(s) for s in all_symbols]
            if tasks:
                try:
                    reports = await asyncio.wait_for(asyncio.gather(*tasks), timeout=40.0)
                except asyncio.TimeoutError:
                    self.logger.error("❌ Global reconciliation gather TIMED OUT after 40s")
                    reports = []
            else:
                reports = []

            self.logger.info(f"[SYNC] ✅ Global reconciliation complete. {len(reports)} symbols processed.")

        except Exception as e:
            self.logger.error(f"❌ Global reconciliation failed: {e}", exc_info=True)

        return reports

    async def reconcile_symbol(self, symbol: str, mode: str = "active") -> Dict[str, Any]:
        """
        Reconcile a single symbol (Individual pass).
        Useful for targeted syncs after manual trades or errors.
        """
        symbol = normalize_symbol(symbol)
        self.logger.info(f"[SYNC] 🔄 Starting individual reconciliation for {symbol} (Mode: {mode})")

        # Fetch for this symbol only
        exchange_positions = await self._fetch_exchange_positions(symbol)
        if exchange_positions is None:
            return {"symbol": symbol, "error": "Fetch error"}

        open_orders = await self.error_handler.execute_with_breaker(
            "reconciliation_fetch", self.adapter.fetch_open_orders, symbol, retry_config=self.reconcile_retry_config
        )
        if open_orders is None:
            return {"symbol": symbol, "error": "Orders fetch error"}

        return await self._reconcile_symbol_data(symbol, exchange_positions, open_orders, mode=mode)

    async def _reconcile_symbol_data(
        self, symbol: str, exchange_positions: List[Dict], open_orders: List[Dict], mode: str = "active"
    ) -> Dict[str, Any]:
        """Core reconciliation logic with pre-provided data."""
        # This is the same logic as reconcile_symbol minus the fetching
        report = {
            "symbol": symbol,
            "positions_checked": 0,
            "positions_fixed": 0,
            "positions_closed": 0,
            "ghosts_removed": 0,
            "orders_cancelled": 0,
            "issues_found": [],
        }

        # Phase 46.1: O(1) Symbol Lookup replaces linear list scan (prevents N^2 growth complexity)
        local_positions = self.tracker.get_positions_by_symbol(symbol)
        report["positions_checked"] = len(local_positions)

        for pos in local_positions[:]:
            # LIFECYCLE: GARBAGE COLLECTION
            # Phase 234: Include CLOSING in GC to handle timed-out close attempts
            if getattr(pos, "status", "") in ["OFF_BOARDING", "CLOSING"]:
                if not self._exists_in_exchange(pos, exchange_positions):
                    # Confirmed gone from exchange -> Cleanup
                    self.logger.info(f"🧹 GC: Finalizing removal of {pos.status} position {pos.trade_id}")
                    await self.tracker.finalize_removal(pos.trade_id)
                    continue
                else:
                    # Still closing on exchange -> Wait, do nothing (Respect State)
                    continue

            if not self._exists_in_exchange(pos, exchange_positions):
                # Phase 57.1: Ghost Protection Grace Period (Prevent killing new positions due to REST lag)
                try:
                    # entry_timestamp is in milliseconds (Binance/CCXT format)
                    entry_time_ms = float(pos.entry_timestamp or 0)
                    if entry_time_ms < 100000000000:  # Detect seconds vs milliseconds
                        entry_time_ms *= 1000
                    now_ms = time.time() * 1000
                    if (now_ms - entry_time_ms) < 60000:  # 60 seconds
                        self.logger.debug(
                            f"⏳ Sync: {pos.trade_id} is GHOST but in 60s grace period. Skipping ghost removal."
                        )
                        continue
                except (ValueError, TypeError):
                    pass

                # Phase 82: Prevent race condition with OCOManager/Manual Close
                # If the position was already closed while we were iterating, skip it
                if not self.tracker.get_position(pos.trade_id):
                    self.logger.debug(f"⏭️ Position {pos.trade_id} vanished during reconciliation (Already handled)")
                    continue

                # ... investigate ghost ...
                self.logger.debug(f"👻 Ghost position found in tracker: {pos.trade_id} (not on exchange)")
                try:
                    investigation_result = await self._investigate_ghost(pos, symbol)
                    if investigation_result:
                        report["positions_closed"] += 1
                    else:
                        self.logger.warning(f"⚠️ Investigation inconclusive for {pos.trade_id}. Removing as Error.")
                        if await self.tracker.remove_position(pos.trade_id):
                            report["ghosts_removed"] += 1
                            report["issues_found"].append(f"ghost_removed:{pos.trade_id}")
                except TransientCommunicationError as t_err:
                    self.logger.warning(
                        f"🕒 Aborting ghost cleanup for {pos.trade_id} due to transient error: {t_err}. "
                        "Will retry in next cycle."
                    )
                    continue  # Skip removal, keep in tracker for next pass
                except Exception as e:
                    self.logger.error(f"❌ Critical error during ghost investigation for {pos.trade_id}: {e}")
                    # Safety removal if it's not a known transient error?
                    # For now, let's be conservative and NOT remove if it crashes.
                continue

            # Corrupt check
            amount = pos.order.get("amount", 0) if pos.order else 0
            if not amount and pos.entry_price > 0 and pos.notional:
                amount = abs(pos.notional) / pos.entry_price
            if not amount or amount <= 0:
                if self.tracker.remove_position(pos.trade_id):
                    report["ghosts_removed"] += 1
                continue

            # Integrity check
            status = getattr(pos, "status", "ACTIVE")
            if status in ["OPENING", "CLOSING", "MODIFYING", "OFF_BOARDING"]:
                continue

            # Phase 51: Naked Protection Grace Period
            # If position is ACTIVE but missing brackets, give it 60 seconds before force-closing.
            # This prevents race conditions where the main order is filled but OCOManager is still creating brackets.
            if status == "ACTIVE":
                try:
                    entry_time_ms = float(pos.entry_timestamp or 0)
                    if entry_time_ms < 100000000000:
                        entry_time_ms *= 1000
                    now_ms = time.time() * 1000
                    if (now_ms - entry_time_ms) < 60000:
                        # self.logger.debug(f"⏳ Sync: {pos.trade_id} is ACTIVE but in 60s grace period. Skipping naked check.")
                        continue
                except (ValueError, TypeError):
                    pass

            # Phase 54: Use PositionTracker as Single Source of Truth for bracket validation
            open_order_ids = {str(o.get("order_id") or o.get("id")) for o in open_orders}
            open_client_ids = {str(o.get("client_order_id")) for o in open_orders if o.get("client_order_id")}
            has_tp, has_sl = self.tracker.has_valid_bracket(pos.trade_id, open_order_ids, open_client_ids)

            if not has_tp or not has_sl:
                # --- CONCURRENCY GRACE PERIOD (Phase 34) ---
                # If a TP/SL order is missing from exchange data, check if it was recently updated/created locally.
                # This prevents "Naked" closure due to exchange REST indexing lag without adding execution lag.
                grace_period = 20.0  # seconds (Phase 120: Increased for MULTI REST lag)
                now = time.time()

                tp_recent = False
                if pos.tp_order and (now - pos.tp_order.last_updated < grace_period):
                    tp_recent = True

                sl_recent = False
                if pos.sl_order and (now - pos.sl_order.last_updated < grace_period):
                    sl_recent = True

                # If the missing order is "newly created/updated", we wait for the next reconciliation cycle
                if (not has_tp and tp_recent) or (not has_sl and sl_recent):
                    self.logger.info(
                        f"⏳ Reconciliation: Potential lag detected for {pos.trade_id} (TP={has_tp}, SL={has_sl}). "
                        "Benefiting from Grace Period (Wait for next cycle)."
                    )
                    continue

                self.logger.warning(f"⚠️ Position {pos.trade_id} is NAKED/BROKEN (TP={has_tp}, SL={has_sl}).")

                # If mode is audit, we just report
                if mode == "audit":
                    report["issues_found"].append(f"naked_detected:{pos.trade_id}")
                    continue

                # Phase 57: Smart Healing (Auto-Repair)
                if pos.order and self.oco_manager:
                    try:
                        self.logger.info(f"🚑 Smart Healing: Attempting to repair naked position {pos.trade_id}...")

                        # Phase 61: Mark as healed before restoration
                        # Phase 69: Defensive attribute setting
                        if hasattr(pos, "healed"):
                            pos.healed = True

                        # Phase 57.4: Explicitly pass which legs are missing to force re-creation
                        healed = await self.oco_manager.restore_bracket(
                            pos, missing_tp=not has_tp, missing_sl=not has_sl
                        )

                        if healed:
                            self.logger.info(f"✨ Smart Healing Successful for {pos.trade_id}. Position saved.")
                            resilience_healing_events_total.labels(symbol=symbol, reason="smart_healing").inc()
                            report["positions_fixed"] += 1
                            continue  # Skip closure
                        else:
                            self.logger.warning(
                                f"⚠️ Smart Healing Failed for {pos.trade_id}. Proceeding to safety close."
                            )
                    except Exception as e:
                        self.logger.error(f"❌ Smart Healing Error: {e}", exc_info=True)

                # Close on exchange immediately
                matched_ex_pos = next(
                    (ep for ep in exchange_positions if normalize_symbol(ep.get("symbol", "")) == symbol), None
                )
                if matched_ex_pos:
                    # Centralized Governance: Request lock before force-closing
                    if await self.tracker.lock_for_closure(pos.trade_id):
                        try:
                            self.logger.warning(f"⛔ Closing NAKED position {pos.trade_id} on exchange for safety.")
                            # Phase 72: Mark OFF_BOARDING to prevent double-accounting (RECON_FORCE + GHOST_REMOVAL)
                            pos.status = "OFF_BOARDING"
                            await self._close_position_dict(matched_ex_pos)
                            report["positions_closed"] += 1
                        finally:
                            self.tracker.unlock(pos.trade_id, position=pos)
                    else:
                        self.logger.info(f"⏭️ Skipping reconciliation close for {pos.trade_id}: Position busy")
                        continue

                if await self.tracker.remove_position(pos.trade_id):
                    report["ghosts_removed"] += 1
                    report["issues_found"].append(f"naked_closed:{pos.trade_id}")

        # 3. ADOPT UNKNOWNS
        for ex_pos in exchange_positions:
            if not self._exists_in_tracker(ex_pos, local_positions):
                if mode == "audit":
                    report["issues_found"].append(f"unknown_detected:{symbol}")
                    continue

                adopted = await self._adopt_position_if_healthy(ex_pos, open_orders, symbol)
                if adopted:
                    report["positions_fixed"] += 1
                else:
                    self.logger.warning(f"⛔ Position unhealthy for {symbol}. Closing for safety.")
                    await self._close_position_dict(ex_pos)
                    report["positions_closed"] += 1

        # 4. CLEANUP ORPHANS
        # Phase 57.5: If mass orphans detect (likely system reset/crash residue), use aggressive cleanup
        orphans_detected = len(open_orders)
        force_orphaned_reset = orphans_detected >= 5
        if force_orphaned_reset:
            self.logger.warning(
                f"🌪️ Mass orphan storm detected for {symbol} ({orphans_detected} orders). Purging immediately."
            )

        cancelled = await self._cleanup_orphaned_orders(
            symbol, open_orders, exchange_positions, mode=mode, orphaned_reset=force_orphaned_reset
        )
        report["orders_cancelled"] = cancelled

        return report

    async def _adopt_position_if_healthy(self, ex_pos: Dict, open_orders: List[Dict], symbol: str) -> bool:
        """
        Attempt to adopt an unknown position IF it is healthy (1 TP, 1 SL).
        Uses Dual-Strategy:
        1. Semantic: Matches C3_TP/SL tags in clientOrderId (High Confidence)
        2. Heuristic: Fallback to price/type logic (Medium Confidence)
        """
        try:
            # 1. Parse position details
            size = abs(float(ex_pos.get("contracts", 0) or ex_pos.get("size", 0) or ex_pos.get("amount", 0)))
            entry_price = float(ex_pos.get("entryPrice", 0))
            side_raw = ex_pos.get("side", "").lower()
            side = "LONG" if side_raw == "long" else "SHORT"

            if size == 0:
                return False

            tp_order = None
            sl_order = None

            # STRATEGY 1: SEMANTIC MATCHING (C3_TP_..., C3_SL_...)
            for order in open_orders:
                client_id = str(order.get("clientOrderId", "") or "")
                prefix = self._parse_client_order_id(client_id)

                if prefix == "TP":
                    if tp_order:
                        return False  # Multiple TPs
                    tp_order = order
                elif prefix == "SL":
                    if sl_order:
                        return False  # Multiple SLs
                    sl_order = order

            if tp_order and sl_order:
                self.logger.info(
                    f"🧬 [Semantic] Adopted healthy position {symbol} (TP={tp_order.get('clientOrderId')}, SL={sl_order.get('clientOrderId')})"
                )
                return self._assimilate_position(ex_pos, symbol, side, size, entry_price, tp_order, sl_order)

            # STRATEGY 2: HEURISTIC FALLBACK (Legacy/Manual)
            self.logger.debug("⚠️ Semantic match failed, attempting heuristic adoption...")
            tp_order = None
            sl_order = None  # Reset

            close_side = "sell" if side == "LONG" else "buy"

            for order in open_orders:
                o_side = order.get("side", "").lower()
                o_type = order.get("type", "").upper()
                client_id = str(order.get("clientOrderId", "") or "")

                # Skip if semantically tagged as ENTRY or other unrelated
                if "ENTRY" in self._parse_client_order_id(client_id):
                    continue

                if o_side != close_side:
                    continue

                if "STOP" in o_type:
                    if sl_order:
                        return False
                    sl_order = order
                elif "LIMIT" in o_type or "TAKE_PROFIT" in o_type:
                    price = float(order.get("price", 0) or order.get("stopPrice", 0))
                    # Basic directional check
                    is_tp = (side == "LONG" and price > entry_price) or (side == "SHORT" and price < entry_price)
                    if is_tp:
                        if tp_order:
                            return False
                        tp_order = order

            if tp_order and sl_order:
                self.logger.info(f"🧬 [Heuristic] Adopted healthy position {symbol}")
                return self._assimilate_position(ex_pos, symbol, side, size, entry_price, tp_order, sl_order)

            self.logger.warning(f"Adoption failed: Missing order (TP={bool(tp_order)}, SL={bool(sl_order)})")
            return False

        except Exception as e:
            self.logger.error(f"Adoption error: {e}")
            return False

    def _assimilate_position(self, ex_pos, symbol, side, size, entry_price, tp_order, sl_order) -> bool:
        """Construct and inject OpenPosition from exchange data."""
        try:
            # UNIQUE ID: Include symbol to prevent collisions during parallel adoption/shutdown
            symbol_safe = symbol.replace("/", "_").replace(":", "_")
            trade_id = f"adopted_{int(time.time())}_{symbol_safe}"

            # Extract Levels
            tp_level = float(tp_order.get("price", 0) or tp_order.get("stopPrice", 0))
            if tp_level == 0:
                tp_level = float(tp_order["info"].get("price", 0)) if "info" in tp_order else 0

            sl_level = float(sl_order.get("stopPrice", 0) or sl_order.get("price", 0))
            if sl_level == 0:
                sl_level = float(sl_order["info"].get("stopPrice", 0)) if "info" in sl_order else 0

            position = OpenPosition(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                entry_timestamp=str(ex_pos.get("timestamp", time.time())),
                margin_used=float(
                    ex_pos.get("initialMargin", 0) or (size * entry_price / float(ex_pos.get("leverage", 1)))
                ),
                notional=float(ex_pos.get("notional", size * entry_price)),
                leverage=float(ex_pos.get("leverage", 1)),
                tp_level=tp_level,
                sl_level=sl_level,
                liquidation_level=float(ex_pos.get("liquidationPrice", 0)),
                order={"method": "adopted", "size": size, "amount": size},
                main_order_id=None,  # Lost
                tp_order_id=str(tp_order.get("client_order_id") or tp_order.get("id")),
                sl_order_id=str(sl_order.get("client_order_id") or sl_order.get("id")),
                exchange_tp_id=str(tp_order.get("algo_id") or tp_order.get("id")),
                exchange_sl_id=str(sl_order.get("algo_id") or sl_order.get("id")),
                bars_held=0,
                status="ACTIVE",  # Assume active if on exchange
            )

            # Inject position into tracker
            self.tracker.add_position(position)

            # Phase 54: Register TP/SL IDs in Alias Map for orphan detection
            tp_exchange_id = str(tp_order.get("order_id") or tp_order.get("id", ""))
            sl_exchange_id = str(sl_order.get("order_id") or sl_order.get("id", ""))
            tp_client_id = str(tp_order.get("client_order_id", ""))
            sl_client_id = str(sl_order.get("client_order_id", ""))

            if tp_exchange_id:
                self.tracker.register_alias(tp_exchange_id, position, symbol=symbol)
            if sl_exchange_id:
                self.tracker.register_alias(sl_exchange_id, position, symbol=symbol)
            if tp_client_id:
                self.tracker.register_alias(tp_client_id, position, symbol=symbol)
            if sl_client_id:
                self.tracker.register_alias(sl_client_id, position, symbol=symbol)

            self.logger.info(f"✅ Position adopted with aliases registered: {trade_id}")
            return True

        except Exception as e:
            self.logger.error(f"Assimilation failed: {e}")
            return False

    async def _investigate_ghost(self, pos: OpenPosition, symbol: str) -> str:
        """
        Investigate a missing 'Ghost' position to determine its fate.
        Returns the resolution string if confirmed, or None if inconclusive.
        """
        try:
            # 1. Check known TP Order
            if pos.tp_order_id:
                try:
                    # Phase 240: Fast Ticker with timeout
                    tp_order = await asyncio.wait_for(self.adapter.fetch_order(pos.tp_order_id, symbol), timeout=5.0)
                    status = tp_order.get("status")
                    filled = float(tp_order.get("filled", 0))

                    # Logic Fix (Phase 91): Only count as TP win if actually filled
                    if status in ["closed", "expired"] and filled > 0:
                        amount = filled
                        price = float(tp_order.get("average", 0) or tp_order.get("price", 0))

                        # Deep Audit: If we have fill but no price (rare), fetch trades
                        if price == 0:
                            self.logger.warning(f"🕵️ Deep Audit triggering for {pos.trade_id} (Filled {filled} @ $0)")
                            trades = await self.adapter.fetch_my_trades(symbol, params={"orderId": pos.tp_order_id})
                            if trades:
                                total_val = sum(t["price"] * t["amount"] for t in trades)
                                total_qty = sum(t["amount"] for t in trades)
                                if total_qty > 0:
                                    price = total_val / total_qty

                        if price > 0:
                            # Confirm close as WIN (EXIT_REASON: TP (Recon))
                            # We manually trigger confirm_close on tracker
                            pnl = (
                                (price - pos.entry_price) * amount
                                if pos.side == "LONG"
                                else (pos.entry_price - price) * amount
                            )

                            # Extract fee from order if available
                            fee_info = tp_order.get("fee", {})
                            exit_fee = float(fee_info.get("cost", 0) if isinstance(fee_info, dict) else 0)

                            self.tracker.confirm_close(
                                pos.trade_id,
                                exit_price=price,
                                exit_reason="TP (Recon)",
                                pnl=pnl,
                                fee=exit_fee,
                                healed=True,
                            )
                            self.logger.info(f"👻 Ghost {pos.trade_id} RESOLVED: TP Order Filled (Deep Audit Verified)")
                            return "TP_FILLED"
                    elif status == "expired" and filled == 0:
                        self.logger.info(f"ℹ️ TP Order {pos.tp_order_id} expired empty. Not the cause of closure.")
                        return "Closed via TP (Confirmed)"
                except Exception as e:
                    if "-2013" in str(e):
                        self.logger.info(
                            f"ℹ️ TP order {pos.tp_order_id} for {pos.trade_id} is missing/archived. High probability of closure."
                        )
                        # Don't return yet, let it fall through to Deep Search Step 3
                    else:
                        self.logger.warning(f"⚠️ Could not fetch TP order {pos.tp_order_id}: {e}")

            # 2. Check known SL Order
            if pos.sl_order_id:
                try:
                    # Phase 240: Fast Ticker with timeout
                    sl_order = await asyncio.wait_for(self.adapter.fetch_order(pos.sl_order_id, symbol), timeout=5.0)
                    # Stop Market orders usually show as 'calnceled' or 'expired' if triggered via algo,
                    # BUT if they triggered a fill, there should be a trade.
                    # Simpler check: If status is 'closed' (filled)
                    if sl_order and sl_order.get("status") in ["closed", "expired"]:
                        # FILLED means LOSS
                        amount = float(sl_order.get("amount", 0))
                        price = float(sl_order.get("price", 0) or sl_order.get("average", 0))

                        if price == 0:
                            price = pos.sl_level  # Fallback to SL level

                        pnl = (
                            (price - pos.entry_price) * amount
                            if pos.side == "LONG"
                            else (pos.entry_price - price) * amount
                        )

                        # Extract fee from order if available
                        fee_info = sl_order.get("fee", {})
                        exit_fee = float(fee_info.get("cost", 0) if isinstance(fee_info, dict) else 0)

                        self.tracker.confirm_close(
                            pos.trade_id,
                            exit_price=price,
                            exit_reason="SL (Recon)",
                            pnl=pnl,
                            fee=exit_fee,
                            healed=True,
                        )
                        return "Closed via SL (Confirmed)"
                except Exception as e:
                    if "-2013" in str(e):
                        self.logger.info(
                            f"ℹ️ SL order {pos.sl_order_id} for {pos.trade_id} is missing/archived. High probability of closure."
                        )
                        # Let it fall through to Step 3
                    else:
                        self.logger.warning(f"⚠️ Could not fetch SL order {pos.sl_order_id}: {e}")

            self.logger.warning(
                f"⚠️ Investigation inconclusive for {pos.trade_id}. Could not confirm close via TP/SL orders."
            )

            # 3. DEEP SEARCH: Check User Trades (Source of Truth)
            # HARDENED: Add defensive checks for malformed trade data
            try:
                # Fetch recent trades for this symbol
                # Phase 82: Increased limit to 100 to handle high-density chaos test runs
                # Phase 240: Fast search with timeout
                trades = await asyncio.wait_for(self.adapter.fetch_my_trades(symbol, limit=100), timeout=10.0)

                # Check for any CLOSING trade after position entry
                entry_time = getattr(pos, "entry_timestamp", 0)
                # Handle string timestamps from state recovery
                if isinstance(entry_time, str):
                    try:
                        entry_time = float(entry_time)
                    except (ValueError, TypeError):
                        entry_time = 0

                # Phase 57.3: Defensive unit detection (s vs ms)
                if entry_time > 0 and entry_time < 100000000000:
                    entry_time *= 1000

                matches = []
                for t in trades:
                    # Defensive check for malformed trade data
                    if not isinstance(t, dict):
                        continue
                    trade_ts = t.get("timestamp", 0)
                    if not isinstance(trade_ts, (int, float)):
                        continue

                    # Filter by time (trade must be AFTER or EQUAL to entry, with 1s buffer for safety)
                    if trade_ts >= (entry_time - 1000):
                        # Filter by side (must be opposite to entry) or by ID
                        close_side = "sell" if pos.side == "LONG" else "buy"
                        order_id = str(t.get("order_id") or t.get("id"))

                        is_match = order_id in [str(pos.main_order_id), str(pos.tp_order_id), str(pos.sl_order_id)] or (
                            t.get("side") == close_side and trade_ts >= entry_time
                        )

                        if is_match:
                            matches.append(t)

                if matches:
                    # Binance docs: default sort is by time (oldest first). So matches[-1] is newest.
                    last_trade = matches[-1]

                    price = float(last_trade.get("price", 0))
                    pnl = float(last_trade.get("realized_pnl", 0))

                    fee_real = float((last_trade.get("fee") or {}).get("cost", 0) or 0)

                    if price > 0:
                        self.logger.info(
                            f"🕵️ Deep Search found closing trade: {last_trade.get('id')} @ {price} "
                            f"(PnL: {pnl}, Fee: {fee_real})"
                        )
                        self.tracker.confirm_close(
                            pos.trade_id,
                            exit_price=price,
                            exit_reason="TRADE_CONFIRMED",
                            pnl=pnl,
                            fee=fee_real,
                            healed=True,
                        )
                        return f"Closed via Trade {last_trade.get('id')} (Deep Confirmed)"

            except Exception as e:
                err_str = str(e).lower()
                # Phase 89: Escalate transient errors so they can be retried in the next reconciliation cycle
                if any(p in err_str for p in ["-1021", "timeout", "timed out", "network error", "connection reset"]):
                    raise TransientCommunicationError(f"Transient error during deep search: {e}")
                self.logger.warning(f"Deep search failed: {e}")

            return None  # Inconclusive

        except Exception as e:
            self.logger.error(f"Error investigating ghost {pos.trade_id}: {e}")
            return None

    def _parse_client_order_id(self, client_id: str) -> str:
        """
        Extract semantic type from clientOrderId.
        C3_TP_... -> TP
        C3_SL_... -> SL
        C3_ENTRY_... -> ENTRY
        """
        if not client_id:
            return ""

        # Phase 41: Recognize CASINO_ prefix
        prefix = "CASINO_"
        if not client_id.startswith(prefix):
            # Try legacy C3_ prefix just in case
            if not client_id.startswith("C3_"):
                return ""
            prefix = "C3_"

        parts = client_id.split("_")
        if len(parts) >= 2:
            return parts[1]  # TP, SL, ENTRY (ENTRY usually followed by 'V3' or similar)
        return ""

    async def _fetch_exchange_positions(self, symbol: str) -> List[Dict]:
        """Fetch positions from exchange with retry."""
        try:
            return await self.error_handler.execute_with_breaker(
                "reconciliation_fetch", self.adapter.fetch_positions, symbol, retry_config=self.reconcile_retry_config
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch exchange positions for {symbol}: {e}")
            return None

    def _exists_in_exchange(self, local_pos, exchange_positions) -> bool:
        """Check if local position exists in exchange list."""
        local_symbol_norm = normalize_symbol(local_pos.symbol).replace("/", "")
        for ex_pos in exchange_positions:
            ex_symbol = normalize_symbol(ex_pos.get("symbol", "")).replace("/", "")
            ex_size = abs(float(ex_pos.get("contracts", 0) or ex_pos.get("size", 0) or ex_pos.get("amount", 0) or 0))
            # Phase 232: Dust Tolerance (0.005 units/contracts)
            # If the residual is too small to be tradable, treated as non-existent to allow tracker cleanup.
            if ex_symbol == local_symbol_norm:
                self.logger.debug(f"🔍 Recon Check: {ex_symbol} | Size: {ex_size} | Tol: 0.005")
                if ex_size > 0.005:
                    return True
        return False

    def _exists_in_tracker(self, exchange_pos: Dict, local_positions: List) -> bool:
        """Check if exchange position exists in local tracker."""
        ex_symbol = normalize_symbol(exchange_pos.get("symbol", "")).replace("/", "")
        ex_size = abs(
            float(exchange_pos.get("contracts", 0) or exchange_pos.get("size", 0) or exchange_pos.get("amount", 0) or 0)
        )

        if ex_size == 0:
            return True  # Treat empty exchange position as "exists" (don't need to adopt nothing)

        # Phase 72: Robust Fuzzy Matching (Standardize separators)
        ex_symbol_clean = ex_symbol.replace(":", "")

        for pos in local_positions:
            local_symbol = normalize_symbol(pos.symbol).replace("/", "").replace(":", "")
            if ex_symbol_clean == local_symbol:
                return True
        return False

    async def _cleanup_orphaned_orders(
        self,
        symbol: str,
        open_orders: List[Dict],
        exchange_positions: List[Dict],
        mode: str = "active",
        orphaned_reset: bool = False,
    ) -> int:
        """
        Cancel orphaned orders (orders without associated position).

        Phase 53: Uses PositionTracker.get_position_by_id() as the Single Source of Truth.
        This eliminates the ID mismatch bug where client IDs were compared against exchange IDs.
        """
        if not open_orders:
            return 0

        # Check if there's any exchange position for this symbol
        has_exchange_position = any(
            normalize_symbol(ep.get("symbol", "")) == symbol and float(ep.get("contracts", 0)) != 0
            for ep in exchange_positions
        )

        # Cancel un-tracked orders
        cancelled_count = 0
        for order in open_orders:
            order_id = str(order.get("id", ""))
            client_order_id = str(order.get("clientOrderId", ""))

            if not order_id:
                continue

            # PHASE 53: Use PositionTracker as Single Source of Truth - Phase 80: Partitioned by Symbol
            # Check if this order (by exchange ID or client ID) is associated with any tracked position
            # We strictly check WITHIN the current reconciliation symbol to prevent cross-symbol hijack
            position = self.tracker.get_position_by_id(order_id, symbol=symbol)
            if not position:
                position = self.tracker.get_position_by_id(client_order_id, symbol=symbol) if client_order_id else None

            # Phase 57.6: Strict Identity Matching
            # An order is only legitimate if it is specifically one of the CURRENT legs
            is_tracked = False
            if position:
                current_ids = {
                    str(position.trade_id),
                    str(position.exchange_tp_id),
                    str(position.tp_order_id),
                    str(position.exchange_sl_id),
                    str(position.sl_order_id),
                }
                if str(order_id) in current_ids or (client_order_id and str(client_order_id) in current_ids):
                    is_tracked = True

            # If order is tracked AND the position exists on exchange, it's legitimate
            if is_tracked:
                # Double-check: If the associated position exists on exchange, order is NOT orphan
                if position and self._exists_in_exchange(position, exchange_positions):
                    continue  # Legitimate order, skip

            # If there's a position on exchange but we don't track this order, be careful
            # It might be a newly created order that hasn't been registered yet
            # Phase 141: Robust Grace Period (60s) for "Young" Orphans
            # This prevents race conditions where RecService sees the order via REST before OCOManager registers it.
            try:
                order_time = int(order.get("time", 0) or order.get("updateTime", 0) or order.get("timestamp", 0))
                if order_time > 0:
                    age_ms = (time.time() * 1000) - order_time
                    if age_ms < 60000:  # 60 seconds
                        # self.logger.debug(f"⏳ Skipping young orphan: {order_id} (Age: {age_ms/1000:.1f}s)")
                        resilience_orphan_skips_total.labels(symbol=symbol, reason="grace_period").inc()
                        continue
            except Exception:
                pass

            if not orphaned_reset and has_exchange_position and client_order_id and "CASINO_" in client_order_id:
                # This is likely our own order that's in-flight; skip for safety
                self.logger.debug(f"⏳ Skipping potential in-flight order: {order_id} ({client_order_id})")
                resilience_orphan_skips_total.labels(symbol=symbol, reason="in_flight_heuristic").inc()
                continue

            # This order is truly orphaned
            # Phase 233: Classify as OCO residual vs true orphan
            # If no exchange position exists for this symbol, the position already
            # closed (via SL/TP fill) and this is just the leftover OCO leg.
            cancel_reason = "oco_residual" if not has_exchange_position else "true_orphan"

            if mode == "audit":
                self.logger.info(f"🕵️ Orphan detected: {order_id} ({cancel_reason}, not cancelled in audit mode)")
                continue

            try:
                # Phase 45: Delegate to OrderExecutor
                if self.croupier and self.croupier.order_executor:
                    await self.croupier.order_executor.cancel_order(order_id, symbol)
                    resilience_orphan_cancels_total.labels(symbol=symbol, reason=cancel_reason).inc()
                    cancelled_count += 1
                else:
                    # Fallback to direct call if for some reason Croupier is missing executor
                    await self.error_handler.execute_with_breaker(
                        "reconciliation_cancel",
                        self.adapter.cancel_order,
                        order_id,
                        symbol,
                        retry_config=self.reconcile_retry_config,
                    )
                    self.logger.info(f"🧹 [Fallback] Cancelled orphaned order: {order_id}")
                    cancelled_count += 1
            except Exception as e:
                # Idempotency: If order doesn't exist (-2011), consider it cancelled
                if "-2011" in str(e) or "Unknown order" in str(e):
                    self.logger.info(f"🧹 Orphan order {order_id} already gone (treated as success)")
                    cancelled_count += 1
                else:
                    self.logger.error(f"❌ Failed to cancel order {order_id}: {e}")

        return cancelled_count

    async def _close_position_dict(self, position_dict: Dict, symbol: Optional[str] = None) -> None:
        """Force close an exchange position (dict format)."""
        try:
            # CRITICAL FIX: Use symbol from position_dict if available to prevent cross-symbol confusion
            target_symbol = position_dict.get("symbol") or symbol
            if not target_symbol:
                self.logger.error("❌ Cannot close position: No symbol provided")
                return

            size = abs(float(position_dict.get("contracts", 0) or position_dict.get("size", 0) or 0))
            if size > 0:
                side_raw = position_dict.get("side", "").lower()
                # force_close_position expects POSITION SIDE (LONG/SHORT)
                position_side = "LONG" if side_raw == "long" else "SHORT"

                if not self.croupier or not self.croupier.order_executor:
                    self.logger.error("❌ Cancellation aborted: No OrderExecutor available in ReconciliationService")
                    return

                # Phase 43: Universal Funnel
                res = await self.croupier.order_executor.force_close_position(
                    symbol=target_symbol, side=position_side, amount=size
                )
                self.logger.info(f"✅ Closed unknown position via Unified Executor: {target_symbol}")

                # PERFECT ACCOUNTING: Record this external closure with forensic enrichment
                try:
                    fill_price = float(res.get("average") or res.get("price") or 0.0)
                    order_id = res.get("id") or res.get("order_id")
                    if fill_price <= 0:
                        # Attempt to get price from fills if available
                        if res.get("fills"):
                            fill_price = float(res["fills"][0].get("price", 0))

                        if fill_price <= 0:
                            fill_price = await self.adapter.get_current_price(target_symbol)

                    raw_entry = float(position_dict.get("entryPrice") or position_dict.get("entry_price") or fill_price)

                    # Phase 35: Standardized Enrichment logic
                    # We record the closure immediately.
                    fee_real = 0.0

                    trade_id = historian.record_external_closure(
                        symbol=target_symbol,
                        side=side_raw.upper(),
                        qty=size,
                        entry_price=raw_entry,
                        exit_price=fill_price,
                        fee=fee_real,
                        reason="RECON_FORCE",
                        session_id=self.tracker.session_id,
                    )

                    # Trigger non-blocking enrichment if trade_id and order_id are present
                    if trade_id and order_id:
                        asyncio.create_task(self.croupier._deferred_fee_enrichment(trade_id, target_symbol))
                except Exception as hist_err:
                    self.logger.error(f"❌ Failed to record external closure in Recon: {hist_err}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")
