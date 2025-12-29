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

import logging
import time
from typing import Any, Dict, List, Optional

from core.error_handling import RetryConfig, get_error_handler
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

    def __init__(self, exchange_adapter, position_tracker: PositionTracker, oco_manager):
        """
        Initialize ReconciliationService.

        Args:
            exchange_adapter: ExchangeAdapter for fetching positions/orders
            position_tracker: PositionTracker instance
            oco_manager: OCOManager for fixing missing TP/SL
        """
        self.adapter = exchange_adapter
        self.tracker = position_tracker
        self.oco_manager = oco_manager
        self.error_handler = get_error_handler()
        self.logger = logging.getLogger("ReconciliationService")

        # Retry config for reconciliation operations
        self.reconcile_retry_config = RetryConfig(max_retries=3, backoff_base=1.0, backoff_factor=2.0, jitter=True)

    async def reconcile_all(self) -> List[Dict[str, Any]]:
        """
        Reconcile ALL symbols in a single optimized pass.
        Fetches all positions and all orders once from the exchange.
        """
        self.logger.info("🔄 Starting global reconciliation for all symbols")
        reports = []

        try:
            # 1. Fetch EVERYTHING (Single pass)
            # Use None to fetch all
            exchange_positions = await self._fetch_exchange_positions(None)
            if exchange_positions is None:
                self.logger.error("❌ Aborting global reconciliation due to fetch error")
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
            for o in open_orders:
                orders_by_symbol[normalize_symbol(o["symbol"])].append(o)

            # Discover all symbols to check (Tracker + Exchange)
            local_symbols = {pos.symbol for pos in self.tracker.open_positions}
            exchange_symbols = {
                normalize_symbol(p["symbol"]) for p in exchange_positions if abs(float(p.get("contracts", 0))) > 1e-8
            }
            all_symbols = local_symbols | exchange_symbols

            for symbol in all_symbols:
                # Reuse the individual symbol logic but with pre-fetched data
                # We need to refactor reconcile_symbol slightly to accept pre-fetched data
                # Or just implement a variant here.
                # To keep it DRY, I'll refactor the core logic into a private method.
                report = await self._reconcile_symbol_data(symbol, ex_pos_by_symbol[symbol], orders_by_symbol[symbol])
                reports.append(report)

            self.logger.info(f"✅ Global reconciliation complete. {len(reports)} symbols processed.")

        except Exception as e:
            self.logger.error(f"❌ Global reconciliation failed: {e}", exc_info=True)

        return reports

    async def reconcile_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Reconcile a single symbol (Individual pass).
        Useful for targeted syncs after manual trades or errors.
        """
        symbol = normalize_symbol(symbol)
        self.logger.info(f"🔄 Starting individual reconciliation for {symbol}")

        # Fetch for this symbol only
        exchange_positions = await self._fetch_exchange_positions(symbol)
        if exchange_positions is None:
            return {"symbol": symbol, "error": "Fetch error"}

        open_orders = await self.error_handler.execute_with_breaker(
            "reconciliation_fetch", self.adapter.fetch_open_orders, symbol, retry_config=self.reconcile_retry_config
        )
        if open_orders is None:
            return {"symbol": symbol, "error": "Orders fetch error"}

        return await self._reconcile_symbol_data(symbol, exchange_positions, open_orders)

    async def _reconcile_symbol_data(
        self, symbol: str, exchange_positions: List[Dict], open_orders: List[Dict]
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

        local_positions = [pos for pos in self.tracker.open_positions if pos.symbol == symbol]
        report["positions_checked"] = len(local_positions)

        # 2. PURGE GHOSTS
        for pos in local_positions[:]:
            if not self._exists_in_exchange(pos, exchange_positions):
                self.logger.warning(f"👻 Ghost position found in tracker: {pos.trade_id} (not on exchange)")
                investigation_result = await self._investigate_ghost(pos, symbol)
                if investigation_result:
                    report["positions_closed"] += 1
                else:
                    self.logger.warning(f"⚠️ Investigation inconclusive for {pos.trade_id}. Removing as Error.")
                    if self.tracker.remove_position(pos.trade_id):
                        report["ghosts_removed"] += 1
                        report["issues_found"].append(f"ghost_removed:{pos.trade_id}")
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
            if status in ["OPENING", "CLOSING"]:
                continue

            open_order_ids = {str(o.get("id")) for o in open_orders}
            has_tp = str(pos.tp_order_id) in open_order_ids
            has_sl = str(pos.sl_order_id) in open_order_ids

            if not has_tp or not has_sl:
                self.logger.warning(f"⚠️ Position {pos.trade_id} is NAKED/BROKEN (TP={has_tp}, SL={has_sl}).")

                # Close on exchange immediately
                matched_ex_pos = next(
                    (ep for ep in exchange_positions if normalize_symbol(ep.get("symbol", "")) == symbol), None
                )
                if matched_ex_pos:
                    self.logger.warning(f"⛔ Closing NAKED position {pos.trade_id} on exchange for safety.")
                    await self._close_position_dict(matched_ex_pos)
                    report["positions_closed"] += 1

                if self.tracker.remove_position(pos.trade_id):
                    report["ghosts_removed"] += 1
                    report["issues_found"].append(f"naked_closed:{pos.trade_id}")

        # 3. ADOPT UNKNOWNS
        for ex_pos in exchange_positions:
            if not self._exists_in_tracker(ex_pos, local_positions):
                adopted = await self._adopt_position_if_healthy(ex_pos, open_orders, symbol)
                if adopted:
                    report["positions_fixed"] += 1
                else:
                    self.logger.warning(f"⛔ Position unhealthy for {symbol}. Closing for safety.")
                    await self._close_position_dict(ex_pos)
                    report["positions_closed"] += 1

        # 4. CLEANUP ORPHANS
        cancelled = await self._cleanup_orphaned_orders(symbol, open_orders, exchange_positions)
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
                tp_order_id=str(tp_order.get("id") or tp_order.get("order_id")),
                sl_order_id=str(sl_order.get("id") or sl_order.get("order_id")),
                bars_held=0,
                status="ACTIVE",  # Assume active if on exchange
            )

            # Inject
            self.tracker.add_position(position)
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
                    tp_order = await self.adapter.fetch_order(pos.tp_order_id, symbol)
                    if tp_order and tp_order.get("status") in ["closed", "expired"]:
                        # FILLED (or Expired FOK) means WIN
                        amount = float(tp_order.get("amount", 0))
                        price = float(tp_order.get("price", 0) or tp_order.get("average", 0))
                        # If price is 0 (e.g. expired without fill info), infer from last price or entry?
                        # Safe fallback to entry if 0 to avoid huge PnL spikes, or better: use last ticker?
                        # For now, if 0, we can't calculate PnL accurately.
                        if price == 0:
                            price = pos.tp_level  # Assume hit TP level if we don't have fill price

                        # Confirm close as WIN (EXIT_REASON: RECONCI_WIN)
                        # We manually trigger confirm_close on tracker
                        pnl = (
                            (price - pos.entry_price) * amount
                            if pos.side == "LONG"
                            else (pos.entry_price - price) * amount
                        )

                        self.tracker.confirm_close(pos.trade_id, exit_price=price, exit_reason="TP (Recon)", pnl=pnl)
                        return "Closed via TP (Confirmed)"
                except Exception as e:
                    self.logger.warning(f"Could not fetch TP order {pos.tp_order_id}: {e}")

            # 2. Check known SL Order
            if pos.sl_order_id:
                try:
                    sl_order = await self.adapter.fetch_order(pos.sl_order_id, symbol)
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

                        self.tracker.confirm_close(pos.trade_id, exit_price=price, exit_reason="SL (Recon)", pnl=pnl)
                        return "Closed via SL (Confirmed)"
                except Exception as e:
                    self.logger.warning(f"Could not fetch SL order {pos.sl_order_id}: {e}")

            self.logger.warning(
                f"⚠️ Investigation inconclusive for {pos.trade_id}. Could not confirm close via TP/SL orders."
            )

            # 3. DEEP SEARCH: Check User Trades (Source of Truth)
            # HARDENED: Add defensive checks for malformed trade data
            try:
                # Fetch recent trades for this symbol
                trades = await self.adapter.fetch_my_trades(symbol, limit=20)

                # Check for any CLOSING trade after position entry
                entry_time = getattr(pos, "entry_timestamp", 0)
                # Handle string timestamps from state recovery
                if isinstance(entry_time, str):
                    try:
                        entry_time = int(entry_time)
                    except (ValueError, TypeError):
                        entry_time = 0

                matches = []
                for t in trades:
                    # Defensive check for malformed trade data
                    if not isinstance(t, dict):
                        continue
                    trade_ts = t.get("timestamp", 0)
                    if not isinstance(trade_ts, (int, float)):
                        continue

                    # Filter by time (trade must be AFTER entry)
                    if trade_ts >= entry_time:
                        # Filter by side (must be opposite to entry)
                        close_side = "sell" if pos.side == "LONG" else "buy"
                        if t.get("side") == close_side:
                            matches.append(t)

                if matches:
                    # Binance docs: default sort is by time (oldest first). So matches[-1] is newest.
                    last_trade = matches[-1]

                    price = float(last_trade.get("price", 0))
                    pnl = float(last_trade.get("realizedPnl", 0))

                    if price > 0:
                        self.logger.info(
                            f"🕵️ Deep Search found closing trade: {last_trade.get('id')} @ {price} (PnL: {pnl})"
                        )
                        self.tracker.confirm_close(
                            pos.trade_id, exit_price=price, exit_reason="TRADE_CONFIRMED", pnl=pnl
                        )
                        return f"Closed via Trade {last_trade.get('id')} (Deep Confirmed)"

            except Exception as e:
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
        if not client_id or not client_id.startswith("C3_"):
            return ""

        parts = client_id.split("_")
        if len(parts) >= 2:
            return parts[1]  # TP, SL, ENTRY
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
            # Basic match: Symbol + Size > 0. Could verify side too.
            if ex_symbol == local_symbol_norm and ex_size > 0:
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

        for pos in local_positions:
            local_symbol = normalize_symbol(pos.symbol).replace("/", "")
            if ex_symbol == local_symbol:
                return True
        return False

    async def _cleanup_orphaned_orders(
        self, symbol: str, open_orders: List[Dict], exchange_positions: List[Dict]
    ) -> int:
        """
        Cancel orphaned orders (orders without associated position).
        Uses pre-fetched data for optimization.
        """
        if not open_orders:
            return 0

        # Check if exchange has open position

        tracked_order_ids = set()

        # Only trust tracker if position actually exists on exchange
        # (Though we likely purged ghosts already, double check safely)
        for pos in self.tracker.open_positions:
            if pos.symbol == symbol:
                if self._exists_in_exchange(pos, exchange_positions):
                    if pos.main_order_id:
                        tracked_order_ids.add(str(pos.main_order_id))
                    if pos.tp_order_id:
                        tracked_order_ids.add(str(pos.tp_order_id))
                    if pos.sl_order_id:
                        tracked_order_ids.add(str(pos.sl_order_id))

        # Cancel un-tracked orders
        cancelled_count = 0
        for order in open_orders:
            order_id = str(order.get("id", ""))
            if order_id and order_id not in tracked_order_ids:
                # Safety: If we have a position but we don't track this order,
                # be careful. But strictly, if it's not in our tracked_ids (which includes adopted ones),
                # it is an orphan.
                try:
                    await self.error_handler.execute_with_breaker(
                        "reconciliation_cancel",
                        self.adapter.cancel_order,
                        order_id,
                        symbol,
                        retry_config=self.reconcile_retry_config,
                    )
                    self.logger.info(f"🧹 Cancelled orphaned order: {order_id}")
                    cancelled_count += 1
                except Exception as e:
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
                close_side = "sell" if side_raw == "long" else "buy"

                try:
                    # Tier 0: Market Close (Standard)
                    await self.adapter.create_market_order(
                        symbol=target_symbol, side=close_side, amount=size, params={"reduceOnly": True}
                    )
                    self.logger.info(f"✅ Closed unknown position: {target_symbol} {size} (Market)")
                except Exception as e:
                    # SMART CLOSE FALLBACK LOGIC
                    err_str = str(e)
                    if "-4131" in err_str:
                        self.logger.warning(
                            f"⚠️ Market Close blocked by -4131. Initiating Smart Close Fallback for {target_symbol}..."
                        )
                        try:
                            current_price = await self.adapter.get_current_price(target_symbol)

                            # Tier 1: Aggressive Limit (+/- 5%)
                            buffer = 0.95 if close_side == "sell" else 1.05
                            limit_price = float(self.adapter.price_to_precision(target_symbol, current_price * buffer))

                            self.logger.info(f"🔄 RecSvc Fallback Tier 1: Limit {limit_price}")
                            try:
                                await self.adapter.create_order(
                                    symbol=target_symbol,
                                    side=close_side,
                                    amount=size,
                                    order_type="limit",
                                    price=limit_price,
                                    params={"timeInForce": "GTC"},
                                )
                                self.logger.info(f"✅ Closed {target_symbol} via Tier 1 LIMIT")
                            except Exception as t1_e:
                                t1_str = str(t1_e)
                                if "-4016" in t1_str or "Limit price can't be" in t1_str:
                                    self.logger.warning(f"⚠️ Tier 1 failed ({t1_str}). Attempting Tier 2 (Regex)...")
                                    import re

                                    match_high = re.search(r"higher than ([\d\.]+)", t1_str)
                                    match_low = re.search(r"lower than ([\d\.]+)", t1_str)

                                    target_price = None
                                    if match_high:
                                        target_price = float(match_high.group(1).rstrip(".")) * 0.999
                                    elif match_low:
                                        target_price = float(match_low.group(1).rstrip(".")) * 1.001

                                    if target_price:
                                        target_price = float(
                                            self.adapter.price_to_precision(target_symbol, target_price)
                                        )
                                        self.logger.info(f"🔄 RecSvc Fallback Tier 2: Limit {target_price}")
                                        await self.adapter.create_order(
                                            symbol=target_symbol,
                                            side=close_side,
                                            amount=size,
                                            order_type="limit",
                                            price=target_price,
                                            params={"timeInForce": "GTC"},
                                        )
                                        self.logger.info(f"✅ Closed {target_symbol} via Tier 2 LIMIT")
                                    else:
                                        raise t1_e
                                else:
                                    raise t1_e
                        except Exception as fallback_e:
                            self.logger.error(f"❌ Smart Close Failed: {fallback_e}")
                            raise e  # Propagate original error
                    else:
                        raise e  # Propagate original error

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")
