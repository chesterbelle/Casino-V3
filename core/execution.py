"""
Execution Layer for Casino-V3.
Handles DecisionEvents from Paroli and executes orders via Croupier.
"""

import asyncio
import logging
import time
from collections import defaultdict

import config.trading
from core.events import EventType, TradeClosedEvent
from core.observability import metrics
from core.portfolio.portfolio_guard import GuardState
from croupier.croupier import Croupier

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Executes trading decisions from Paroli.
    Subscribes to DECISION events (from Paroli).
    """

    def __init__(self, engine, croupier: Croupier, paroli=None, tracker=None):
        self.engine = engine
        self.croupier = croupier
        self.paroli = paroli
        self.tracker = tracker  # SensorTracker instance
        self.active = False
        self.pending_trades = {}  # trade_id -> (decision, sensor_id)
        self.processed_decisions = set()  # Track processed decision IDs to prevent duplicates

        # Phase 2360: Limit Sniper State
        self.pre_flight_orders = {}  # symbol -> {order_id, entry_price, side, timestamp}
        self.last_pre_flight_ts = defaultdict(float)

        # Subscribe to DECISION events (from AdaptivePlayer)
        self.engine.subscribe(EventType.DECISION, self.on_decision)

        # Subscribe to CANDLE events to check for TP/SL exits
        self.engine.subscribe(EventType.CANDLE, self.on_candle)

        # Subscribe to TRADE_CLOSED events to update Paroli/Tracker (Unified Architecture)
        self.engine.subscribe(EventType.TRADE_CLOSED, self.on_trade_closed)

    async def start(self):
        """Start the Order Manager."""
        self.active = True
        logger.info("🚀 OrderManager started")

        # Force reconciliation on startup to restore PositionTracker state
        # This is CRITICAL for OCO callback to work if there are existing positions
        try:
            symbol = self.croupier.exchange_adapter.symbol
            if symbol == "MULTI":
                logger.info("ℹ️ OrderManager: Skipping auto-reconciliation in MULTI mode (handled by main)")
            else:
                logger.info(f"🔄 Startup Reconciliation for {symbol}...")
                await self.croupier.reconcile_positions(symbol)
        except Exception as e:
            logger.error(f"❌ Startup Reconciliation failed: {e}")

    async def stop(self):
        """Stop the Order Manager."""
        self.active = False
        logger.info("🛑 OrderManager stopped")

    async def on_decision(self, event):
        """Handle trading decision from Paroli."""
        if not self.active:
            return

        # Bridge: DecisionEvent structure
        symbol = event.symbol
        side = event.side
        bet_size = event.bet_size

        if side == "SKIP":
            return

        # Phase 2360: Limit Sniper Dispatch
        # DISABLED: PreFlight signal generation removed in Phase 1200 redesign.
        # Limit Sniper now only changes order TYPE (market→limit) on existing LTA signals.
        # See _execute_main_order in oco_manager.py for the new implementation.
        # is_pre_flight = getattr(event, "metadata", {}).get("is_pre_flight", False)
        # if is_pre_flight:
        #     await self._handle_pre_flight(event)
        #     return

        # Phase 2360: Sniper Confirmation Check
        # DISABLED: No longer needed — we don't pre-position orders anymore.
        # pre_order = self.pre_flight_orders.get(symbol)
        # if pre_order and pre_order["side"] == side:
        #     ...

        logger.info(
            f"📩 Decision Received (V4): {symbol} {side} "
            f"(Bet: {bet_size:.2%}, Sensor: {getattr(event, 'selected_sensor', 'N/A')})"
        )

        # Check for duplicate decision processing
        decision_id = getattr(event, "decision_id", None)
        if decision_id:
            if decision_id in self.processed_decisions:
                logger.warning(f"⚠️ DUPLICATE DECISION DETECTED: {decision_id} - SKIPPING")
                return
            self.processed_decisions.add(decision_id)
            logger.debug(f"📥 Processing DecisionEvent {decision_id}")

        # Phase 249: PortfolioGuard entry gate
        guard = getattr(self.croupier, "portfolio_guard", None)
        if guard and guard.state >= GuardState.CAUTION:
            logger.warning(f"🛡️ GUARD: Rejecting entry for {symbol} " f"(state={guard.state.name})")
            return

        # Phase 800: Absolute TP/SL prices (primary path)
        tp_price = getattr(event, "tp_price", None)
        sl_price = getattr(event, "sl_price", None)

        # Fallback: compute from config decimal percentages + estimated price
        # (tp_price/sl_price will be finalized after we have current_price below)
        bet_size = getattr(event, "bet_size", 0.01)

        # Get current equity from croupier
        current_equity = self.croupier.get_equity()

        # Mode 1: Fixed Notional (Default) -> Size = Equity * Bet_Size
        # Mode 2: Fixed Risk -> Size = (Equity * Bet_Size) / SL_Distance
        sizing_mode = getattr(config.trading, "POSITION_SIZING_MODE", "FIXED_NOTIONAL")

        # Calculate sizing via centralized OrderExecutor logic (Phase 46)
        try:
            # Phase 230: Fast-Track Pricing (<1ms vs ~300ms)
            # Priority: estimated_price (DecisionEvent) -> metadata["price"] (AggregatedSignalEvent)
            current_price = getattr(event, "estimated_price", None)
            if not current_price or current_price <= 0:
                metadata = getattr(event, "metadata", None) or {}
                current_price = metadata.get("price")

            # Phase 240: Hard-bypass REST for fast-tracked HFT signals
            is_fast_track = getattr(event, "fast_track", False)

            if is_fast_track and current_price and current_price > 0:
                logger.debug(
                    f"⚡ FAST-TRACK: Bypassing price cache check for {symbol}, using estimated {current_price}"
                )
            else:
                if (
                    not current_price
                    or current_price <= 0
                    or self.croupier.exchange_adapter.is_cache_stale(symbol, check_order_book=False)
                ):
                    if is_fast_track:
                        logger.warning(
                            "⚡ FAST-TRACK ALERT: Cache is stale but avoiding REST call to preserve latency. Using last known cached price."
                        )
                        current_price = self.croupier.exchange_adapter.get_cached_price(symbol)
                        if not current_price:
                            logger.error(
                                f"❌ FAST-TRACK FALLED: No cached price available for {symbol}, forced to REST."
                            )
                            current_price = await self.croupier.exchange_adapter.get_current_price(symbol)
                    else:
                        logger.info(f"💾 Cache Miss/Stale for {symbol}, falling back to REST price lookup...")
                        current_price = await self.croupier.exchange_adapter.get_current_price(symbol)

            position_value, amount = self.croupier.order_executor.calculate_sizing(
                symbol=symbol,
                bet_size=bet_size,
                current_equity=current_equity,
                current_price=current_price,
                sl_pct=config.trading.DEFAULT_SL_PCT,
                sizing_mode=sizing_mode,
            )

            # Phase 800: Compute fallback TP/SL prices if strategy didn't provide them
            if not tp_price or not sl_price:
                tp_pct = config.trading.DEFAULT_TP_PCT
                sl_pct = config.trading.DEFAULT_SL_PCT
                if current_price and current_price > 0:
                    if side == "LONG":
                        tp_price = current_price * (1 + tp_pct)
                        sl_price = current_price * (1 - sl_pct)
                    else:  # SHORT
                        tp_price = current_price * (1 - tp_pct)
                        sl_price = current_price * (1 + sl_pct)
                    logger.info(
                        f"📐 Config fallback TP/SL: TP={tp_price:.4f} SL={sl_price:.4f} "
                        f"(±{tp_pct:.3%}/{sl_pct:.3%} from {current_price:.2f})"
                    )
        except Exception as e:
            logger.error(f"❌ Sizing calculation failed for {symbol}: {e}")
            return

        # Phase 800: Pre-Flight Slippage Math Check
        # Reject the decision BEFORE executing if the live current_price has already
        # slipped past the structural TP/SL (causing Math Inversion).
        if tp_price and sl_price and current_price and current_price > 0:
            is_inverted = False
            if side == "LONG":
                if tp_price <= current_price or sl_price >= current_price:
                    is_inverted = True
            elif side == "SHORT":
                if tp_price >= current_price or sl_price <= current_price:
                    is_inverted = True

            if is_inverted:
                logger.warning(
                    f"🚫 PRE-FLIGHT REJECT (Slippage/Math Inversion) | {symbol} {side} @ {current_price:.4f} | "
                    f"Signal TP: {tp_price:.4f} | Signal SL: {sl_price:.4f}. "
                    f"Market has moved past our targets since signal generation. "
                    f"Discarding trade to save capital."
                )
                return

        # Phase 249: Min Notional Solvency Gate
        try:
            min_notional = self.croupier.exchange_adapter.get_min_notional(symbol)
        except Exception:
            min_notional = 20.0  # Safe default for Binance Futures

        if position_value < min_notional:
            logger.error(
                f"❌ SIZING VIOLATION: {symbol} notional ${position_value:.2f} < "
                f"min ${min_notional:.2f}. Balance too low to trade."
            )
            guard = getattr(self.croupier, "portfolio_guard", None)
            if guard:
                # event.timestamp is usually a string from market data, ensure it's float
                ts = float(event.timestamp) if hasattr(event, "timestamp") else None
                guard.on_sizing_violation(symbol, position_value, min_notional, timestamp=ts)
            return

        # Validate minimum amount after precision rounding
        if amount <= 0:
            logger.error(
                f"❌ Order too small after precision rounding: "
                f"Value={position_value:.2f} | Price={current_price:.2f} | Amount={amount:.8f} | "
                f"Equity={current_equity:.2f} | BetSize={bet_size:.2%} | "
                f"Suggestion: Increase bet size or use higher equity"
            )
            # Phase 249.2: Notify guard of rounding down to zero
            guard = getattr(self.croupier, "portfolio_guard", None)
            if guard:
                ts = float(event.timestamp) if hasattr(event, "timestamp") else None
                guard.on_sizing_violation(symbol, position_value, 0.0, timestamp=ts)  # 0.0 signals rounding fail
            return

        logger.info(
            f"📊 Hardened Sizing: Equity={current_equity:.2f} | "
            f"BetSize={bet_size:.2%} | Value={position_value:.2f} | "
            f"Price={current_price:.2f} | Amount={amount:.8f}"
        )

        # Phase 4: Absorption V1 - Recalculate TP dynamically just before execution
        strategy = getattr(event, "metadata", {}).get("strategy", "")
        if strategy == "AbsorptionScalpingV1":
            tp_price, sl_price = await self._recalculate_absorption_tp(
                event, symbol, side, current_price, tp_price, sl_price
            )

        trade_id = f"V3_{int(time.time()*1000)}"

        # Phase 1200: Limit Sniper — extract structural level price for limit entry
        # When LIMIT_SNIPER_ENABLED, we place limit orders at the structural level (VAL/VAH)
        # instead of market orders. This gives maker fee rate (0.02% vs 0.05%).
        limit_price = None
        if getattr(config.trading, "LIMIT_SNIPER_ENABLED", False):
            # DecisionEvent carries structural data in trigger_level and initial_narrative
            limit_price = getattr(event, "trigger_level", None)
            # Fallback: derive from val/vah in initial_narrative
            if not limit_price or limit_price <= 0:
                narrative = getattr(event, "initial_narrative", None) or {}
                val = narrative.get("val")
                vah = narrative.get("vah")
                if side == "LONG" and val and val > 0:
                    limit_price = val
                elif side == "SHORT" and vah and vah > 0:
                    limit_price = vah

        order_payload = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,  # LONG/SHORT (AdaptivePlayer provides this)
            "size": bet_size,
            "amount": amount,
            "tp_price": tp_price,  # Phase 800: Absolute price
            "sl_price": sl_price,  # Phase 800: Absolute price
            "timestamp": str(event.timestamp),
            "t0_signal_ts": getattr(event, "t0_timestamp", None),  # Phase 85: Signal Latency
            "t1_decision_ts": getattr(event, "t1_decision_ts", None),  # Phase 10: Decision Latency
            "ghost": False,
            "contributors": [getattr(event, "selected_sensor", "Unknown")],
            "trace_id": getattr(event, "trace_id", None),
            "setup_type": getattr(event, "setup_type", "unknown"),
            "estimated_price": current_price,  # Phase 240: avoid redundant price fetch in OCO
            "atr_1m": getattr(event, "atr_1m", 0.0),
            "shadow_sl_activation": getattr(event, "shadow_sl_activation", 0.0025),  # Phase 800
            "limit_price": limit_price,  # Phase 1200: Limit Sniper structural level
        }

        # Phase 650: Explicitly propagate setup_type and latency telemetry for adapters
        order_payload["params"] = {
            "setup_type": order_payload["setup_type"],
            "trace_id": order_payload["trace_id"],
            "t0_signal_ts": order_payload["t0_signal_ts"],
            "t1_decision_ts": order_payload["t1_decision_ts"],
            "t2_submit_ts": time.time(),  # Capture exact wire-time for T2
        }

        # Store for outcome tracking (include sensor_id if available)
        sensor_id = getattr(event, "selected_sensor", "Unknown")
        self.pending_trades[trade_id] = (event, sensor_id)

        # Phase 240: Direct execution with hard timeout cap (no double error-handler wrapping)
        # OCOManager already has its own retry/breaker logic per leg.
        # Double-wrapping caused stalls up to 30s on backoff — catastrophic for HFT.
        try:
            result = await asyncio.wait_for(
                self.croupier.execute_order(order_payload),
                timeout=15.0,  # Hard cap: 15s total for entire OCO bracket
            )

            # Check for success (support both simple orders and OCO bracket results)
            is_success = False
            if result.get("status") in ["filled", "optimistic_sent"]:
                is_success = True
            elif result.get("position") or (result.get("fill_price") and result.get("fill_price") > 0):
                is_success = True

            if is_success:
                logger.info(f"✅ Order Executed: {result.get('id') or result.get('main_order', {}).get('id')}")
                # Record successful order
                metrics.record_order_filled(
                    exchange=self.croupier.exchange_adapter.connector.__class__.__name__.replace("NativeConnector", ""),
                    symbol=event.symbol,
                    side=event.side,
                )
            else:
                logger.warning(f"⚠️ Order Result: {result}")

        except asyncio.TimeoutError:
            logger.error(f"❌ Order timed out (15s cap) for {event.symbol} — dropping")
            metrics.record_order_failed(
                exchange=self.croupier.exchange_adapter.connector.__class__.__name__.replace("NativeConnector", ""),
                reason="timeout_15s",
            )
        except Exception as e:
            logger.error(f"❌ Execution Failed: {e}", exc_info=True)
            metrics.record_order_failed(
                exchange=self.croupier.exchange_adapter.connector.__class__.__name__.replace("NativeConnector", ""),
                reason=str(e)[:50],
            )

    async def _handle_pre_flight(self, event):
        """Phase 2360: Pre-position a LIMIT POST-ONLY order."""
        symbol = event.symbol
        side = event.side
        metadata = event.metadata
        entry_price = metadata.get("entry_price")

        # 1. Cooldown for Pre-Flight (10s) to avoid order book spam
        now = time.time()
        if now - self.last_pre_flight_ts[symbol] < 10.0:
            return

        # 2. Check if we already have a pre-order for this symbol
        if symbol in self.pre_flight_orders:
            return

        logger.warning(f"🏹 [PRE-FLIGHT_SNIPER] Pre-positioning LIMIT {side} for {symbol} @ {entry_price:.4f}")

        # 3. Sizing (Standard 1.0 multiplier for pre-flight, will be adjusted on fill/confirm)
        current_equity = self.croupier.get_equity()
        sizing_mode = getattr(config.trading, "POSITION_SIZING_MODE", "FIXED_NOTIONAL")

        _, amount = self.croupier.order_executor.calculate_sizing(
            symbol=symbol,
            bet_size=0.01,  # Default base bet
            current_equity=current_equity,
            current_price=entry_price,
            sl_pct=config.trading.DEFAULT_SL_PCT,
            sizing_mode=sizing_mode,
        )

        if amount <= 0:
            return

        # 4. Prepare Payload for POST-ONLY LIMIT
        trade_id = f"SNIPER_{int(time.time()*1000)}"
        order_payload = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "type": "limit",
            "amount": amount,
            "price": entry_price,
            "post_only": True,  # CRITICAL: Ensure we are MAKER
            "tp_price": metadata.get("tp_price"),
            "sl_price": metadata.get("sl_price"),
            "is_pre_flight": True,
        }

        # 5. Execute
        self.last_pre_flight_ts[symbol] = now
        try:
            result = await self.croupier.execute_order(order_payload)
            if result.get("status") in ["filled", "optimistic_sent", "open"]:
                order_id = result.get("id") or trade_id
                self.pre_flight_orders[symbol] = {
                    "trade_id": trade_id,
                    "order_id": order_id,
                    "side": side,
                    "timestamp": now,
                    "confirmed": False,
                }
                # Schedule micro-cancellation if not confirmed in 500ms
                asyncio.create_task(self._micro_cancel_if_unconfirmed(symbol, trade_id))
        except Exception as e:
            logger.error(f"❌ Pre-flight execution failed: {e}")

    async def _micro_cancel_if_unconfirmed(self, symbol: str, trade_id: str):
        """Phase 2360: The Micro-Canceller. Tirar del cable si la señal no llega."""
        # Get wait window from config
        wait_sec = getattr(config.trading, "LIMIT_SNIPER_CONFIRM_WINDOW_SEC", 0.5)
        await asyncio.sleep(wait_sec)

        pre_order = self.pre_flight_orders.get(symbol)
        if pre_order and pre_order["trade_id"] == trade_id:
            if not pre_order.get("confirmed", False):
                logger.info(f"🔌 [MICRO-CANCEL] Signal did not arrive for {symbol} sniper. Pulling the plug.")
                try:
                    await self.croupier.close_position(trade_id)  # This will cancel the limit order
                except Exception:
                    pass

            # Cleanup
            self.pre_flight_orders.pop(symbol, None)

    def handle_trade_outcome(self, trade_id: str, won: bool, pnl: float = 0.0):
        """
        Callback when trade closes - update Paroli and SensorTracker.

        Args:
            trade_id: Trade identifier
            won: True if trade was profitable
            pnl: Profit/Loss amount
        """
        if trade_id in self.pending_trades:
            event, sensor_id = self.pending_trades[trade_id]

            # Update Paroli
            if self.paroli:
                self.paroli.handle_trade_outcome(trade_id, won)

            # Update SensorTracker
            if self.tracker and sensor_id != "Unknown":
                self.tracker.update_sensor(sensor_id, pnl, won)
                logger.debug(f"📊 Updated tracker for {sensor_id}: won={won}, pnl={pnl:.4f}")

            # Clean up
            del self.pending_trades[trade_id]

    async def on_trade_closed(self, event: TradeClosedEvent):
        """Handle unified trade closure event to update execution state."""
        logger.info(
            f"📊 Trade Closed Callback: {event.trade_id} | {event.exit_reason} | Won: {event.won} | PnL: {event.pnl:.2f}"
        )
        self.handle_trade_outcome(event.trade_id, event.won, event.pnl)

    async def on_candle(self, event):
        """Handle new candle to check for potential exits."""
        if not self.active:
            return

        # Convert event to dict for Croupier
        candle_dict = {
            "timestamp": event.timestamp,
            "open": event.open,
            "high": event.high,
            "low": event.low,
            "close": event.close,
            "volume": event.volume,
            "market": event.symbol,
            "timeframe": "1m",  # Assuming 1m for now
        }

        # Check for potential exits (TP/SL touched via candle analysis)
        potential_exits = self.croupier.position_tracker.check_and_close_positions(candle_dict)

        # Determine execution mode - CRITICAL for preventing simulated closures
        mode = "testing"  # Default to testing if detection fails
        try:
            if hasattr(self.croupier.exchange_adapter, "connector"):
                connector = self.croupier.exchange_adapter.connector
                mode = getattr(connector, "mode", "testing")
                logger.debug(f"🔍 Mode detected from connector: {mode}")
            else:
                logger.warning("⚠️ exchange_adapter has no connector attribute, defaulting to testing mode")
        except Exception as e:
            logger.error(f"❌ Error detecting mode: {e}, defaulting to testing mode")

        # Log mode for debugging
        logger.debug(f"🎯 Execution mode for this candle: {mode}")

        for exit_info in potential_exits:
            trade_id = exit_info["trade_id"]
            exit_reason = exit_info["exit_reason_detected"]

            # Unified Execution Architecture:
            # All modes (Live, Demo, Backtest) follow the same execution funnel.
            # 1. Internal Exits (TIME, MANUAL) are executed by OrderManager.
            # 2. Exchange Exits (TP, SL, LIQ) are managed by the exchange and waited for.

            # Case 1: Internal Exits (TIME_EXIT, MANUAL_SYNC, etc.)
            if exit_reason in ["TIME_EXIT", "MANUAL_SYNC", "FORCE_CLOSE"]:
                logger.info(f"⏳ Executing {exit_reason} for {trade_id} in {mode} mode")
                try:
                    # close_position handles bracket cancellation and market exit
                    await self.croupier.close_position(trade_id)
                    logger.info(f"✅ {exit_reason} executed successfully for {trade_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to execute {exit_reason} for {trade_id}: {e}")

            # Case 2: Exchange Exits (TP, SL, LIQUIDATION)
            # We skip detection here and wait for Fill/Callback (real WS or VirtualExchange event).
            elif exit_reason in ["TP", "SL", "LIQUIDATION"]:
                logger.debug(f"⏭️ Skipping {exit_reason} detection in {mode} mode - delegating to exchange engine")
                continue

    async def _recalculate_absorption_tp(
        self, event, symbol: str, side: str, current_price: float, original_tp: float, original_sl: float
    ) -> tuple:
        """
        Phase 4: Recalculate TP for Absorption V1 using fresh Footprint data.

        This ensures TP is based on the most recent volume profile (< 50ms old)
        rather than stale data from signal generation (potentially seconds old).

        Args:
            event: DecisionEvent with absorption metadata
            symbol: Trading symbol
            side: LONG or SHORT
            current_price: Current market price
            original_tp: TP calculated at signal time
            original_sl: SL calculated at signal time

        Returns:
            Tuple of (tp_price, sl_price) - recalculated or original if recalc fails
        """
        t1a_start = time.time()

        try:
            from core.footprint_registry import footprint_registry  # noqa: F401
            from decision.absorption_setup_engine import AbsorptionSetupEngine

            # Get absorption metadata
            metadata = getattr(event, "metadata", {})
            absorption_level = metadata.get("absorption_level", 0.0)
            direction = metadata.get("direction", "")

            if not absorption_level or not direction:
                logger.debug("[ABSORPTION] Missing metadata for TP recalc, using original TP")
                return original_tp, original_sl

            # Create temporary engine instance for TP calculation
            # (We could cache this in __init__ but it's lightweight)
            engine = AbsorptionSetupEngine()

            # Recalculate TP using fresh footprint
            new_tp = engine._calculate_tp(symbol, absorption_level, direction, current_price)

            if new_tp is None:
                logger.debug("[ABSORPTION] TP recalc failed, using original TP")
                return original_tp, original_sl

            # Validate TP distance (must be within acceptable range)
            tp_distance_pct = abs(new_tp - current_price) / current_price * 100

            if tp_distance_pct < engine.min_tp_distance_pct:
                logger.debug("[ABSORPTION] Recalc TP too close (%.2f%%), using original TP", tp_distance_pct)
                return original_tp, original_sl

            if tp_distance_pct > engine.max_tp_distance_pct:
                logger.debug("[ABSORPTION] Recalc TP too far (%.2f%%), using original TP", tp_distance_pct)
                return original_tp, original_sl

            # Calculate latency
            t1a_end = time.time()
            latency_ms = (t1a_end - t1a_start) * 1000

            # Log telemetry
            if latency_ms > 50:
                logger.warning(f"⚠️ [LATENCY] TP recalc slow: {latency_ms:.2f}ms (target < 50ms)")
            else:
                logger.debug(f"⚡ [LATENCY] TP recalc: {latency_ms:.2f}ms")

            # Log TP adjustment
            tp_change_pct = abs(new_tp - original_tp) / original_tp * 100
            logger.info(
                f"🎯 [ABSORPTION] TP recalculated: {original_tp:.2f} → {new_tp:.2f} "
                f"({tp_change_pct:+.2f}% change, {latency_ms:.1f}ms)"
            )

            return new_tp, original_sl

        except Exception as e:
            logger.error(f"❌ [ABSORPTION] TP recalc failed: {e}", exc_info=True)
            return original_tp, original_sl
