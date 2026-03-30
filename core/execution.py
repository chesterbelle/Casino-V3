"""
Execution Layer for Casino-V3.
Handles DecisionEvents from Paroli and executes orders via Croupier.
"""

import asyncio
import logging
import time

import config.trading
from core.events import EventType
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

        # Subscribe to DECISION events (from AdaptivePlayer)
        self.engine.subscribe(EventType.DECISION, self.on_decision)

        # Subscribe to CANDLE events to check for TP/SL exits
        self.engine.subscribe(EventType.CANDLE, self.on_candle)

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

        trade_id = f"V3_{int(time.time()*1000)}"

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
            "estimated_price": current_price,  # Phase 240: avoid redundant price fetch in OCO
            "atr_1m": getattr(event, "atr_1m", 0.0),
            "shadow_sl_activation": getattr(event, "shadow_sl_activation", 0.0025),  # Phase 800
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
            exit_price = exit_info["exit_price_detected"]

            # LIVE / DEMO MODE HANDLING
            if mode in ["live", "demo"]:
                # Case 1: Internal Exits (TIME_EXIT, MANUAL, etc.)
                # These are NOT handled by the exchange automatically, so we MUST execute them.
                if exit_reason in ["TIME_EXIT", "MANUAL_SYNC", "FORCE_CLOSE"]:
                    logger.info(f"⏳ Executing {exit_reason} for {trade_id} in {mode} mode")
                    try:
                        # close_position will:
                        # 1. Cancel TP/SL orders
                        # 2. Execute Market Close (ReduceOnly)
                        # 3. Confirm close in tracker
                        await self.croupier.close_position(trade_id)

                        # Update Paroli/Tracker is handled by the callback registered in main.py
                        # But we might want to log here
                        logger.info(f"✅ {exit_reason} executed successfully for {trade_id}")

                    except Exception as e:
                        logger.error(f"❌ Failed to execute {exit_reason} for {trade_id}: {e}")

                # Case 2: Exchange Exits (TP, SL, LIQUIDATION)
                # These ARE handled by the exchange (Limit/Stop orders).
                # We should NOT simulate them here. We wait for WebSocket confirmation.
                elif exit_reason in ["TP", "SL", "LIQUIDATION"]:
                    logger.debug(f"⏭️ Skipping {exit_reason} detection in {mode} mode - waiting for WebSocket")
                    continue

            # TESTING / BACKTEST MODE HANDLING
            else:
                # In Backtest, we trust the candle data and confirm immediately

                # Calculate PnL
                position = self.croupier.position_tracker.get_position(trade_id)
                if not position:
                    continue

                # Protección contra división por cero
                if position.entry_price == 0:
                    logger.warning(f"⚠️ Position {trade_id} has entry_price=0, using exit_price as fallback")
                    pnl_pct = 0.0
                    pnl = 0.0
                else:
                    if position.side == "LONG":
                        pnl_pct = (exit_price - position.entry_price) / position.entry_price
                    else:
                        pnl_pct = (position.entry_price - exit_price) / position.entry_price

                    # Calculate PnL - use notional if available, else estimate from typical position size
                    if position.notional and position.notional > 0:
                        pnl = position.notional * pnl_pct
                    else:
                        # Fallback: estimate notional from typical bet size (1% of 10000 = 100)
                        estimated_notional = 100.0  # Typical small bet
                        pnl = estimated_notional * pnl_pct

                # Calculate fee (0.06% taker fee on notional)
                fee = position.notional * 0.0006

                # Confirm close
                result = self.croupier.position_tracker.confirm_close(
                    trade_id=trade_id,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    pnl=pnl,
                    fee=fee,
                )

                if result:
                    logger.info(f"✅ Trade Closed (Simulated): {trade_id} | {exit_reason} | PnL: {pnl:.2f}")
                    # Update Paroli and Tracker
                    won = result["result"] == "WIN"
                    self.handle_trade_outcome(trade_id, won, pnl)
