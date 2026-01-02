"""
Execution Layer for Casino-V3.
Handles DecisionEvents from Paroli and executes orders via Croupier.
"""

import logging
import time

import config.trading
from core.events import EventType
from core.observability import metrics
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

        # LAYER 2 ATOMICITY PROTECTION: Conditional validation (only if Layer 1 fails)
        self.validation_needed = False  # Flag set when cancellation errors occur
        self.validation_candle_count = 0
        self.validation_interval = 5  # Run validation every 5 candles if needed

        # Subscribe to DECISION events (will come from Paroli)
        self.engine.subscribe(EventType.SYSTEM, self.on_decision)  # Using SYSTEM for now

        # Subscribe to DECISION events (will come from Paroli)
        self.engine.subscribe(EventType.SYSTEM, self.on_decision)  # Using SYSTEM for now

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

        # Check if this is a DecisionEvent (has bet_size attribute)
        if not hasattr(event, "bet_size"):
            return

        if event.side == "SKIP":
            logger.info("⏭️ Decision: SKIP - no trade")
            return

        logger.info(
            f"📩 Decision Received: {event.symbol} {event.side} "
            f"(Size: {event.bet_size:.2%}, Step: {event.paroli_step})"
        )

        # Check for duplicate decision processing
        decision_id = getattr(event, "decision_id", None)
        if decision_id:
            if decision_id in self.processed_decisions:
                logger.warning(f"⚠️ DUPLICATE DECISION DETECTED: {decision_id} - SKIPPING")
                return
            self.processed_decisions.add(decision_id)
            logger.debug(f"📥 Processing DecisionEvent {decision_id}")

        # Construct Order Payload
        trade_id = f"V3_{int(time.time()*1000)}"

        # Calculate multipliers from config or event
        tp_pct = getattr(event, "tp_pct", None) or config.trading.TAKE_PROFIT
        sl_pct = getattr(event, "sl_pct", None) or config.trading.STOP_LOSS

        # Calculate amount from size (fraction of equity)
        # Get current equity from croupier
        current_equity = self.croupier.get_equity()

        # SIZING LOGIC
        # Mode 1: Fixed Notional (Default) -> Size = Equity * Bet_Size
        # Mode 2: Fixed Risk -> Size = (Equity * Bet_Size) / SL_Distance
        sizing_mode = getattr(config.trading, "POSITION_SIZING_MODE", "FIXED_NOTIONAL")

        if sizing_mode == "FIXED_RISK":
            if sl_pct <= 0:
                logger.error(f"❌ Fixed Risk Sizing requires positive Stop Loss % (got {sl_pct})")
                return

            risk_amount = current_equity * event.bet_size
            position_value = risk_amount / sl_pct
            logger.info(
                f"⚖️ OrderManager: Risk={risk_amount:.2f} ({event.bet_size:.2%}) | SL={sl_pct:.2%} | Notional={position_value:.2f}"
            )

        else:  # FIXED_NOTIONAL
            position_value = current_equity * event.bet_size  # Value in USDT

        # Get current price to calculate amount in contracts
        try:
            current_price = await self.croupier.exchange_adapter.get_current_price(event.symbol)
        except Exception as e:
            logger.error(f"❌ Failed to get current price for {event.symbol}: {e}")
            return

        # Calculate amount in contracts (for BTC/USDT, 1 contract = 1 BTC worth of notional)
        # For perpetuals: amount = position_value / price
        amount_raw = position_value / current_price

        # Round to exchange precision (Binance has specific precision requirements)
        amount = float(self.croupier.exchange_adapter.amount_to_precision(event.symbol, amount_raw))

        # Validate minimum amount after precision rounding
        if amount <= 0:
            logger.error(
                f"❌ Order too small after precision rounding: "
                f"raw={amount_raw:.12f} → rounded={amount:.8f} | "
                f"Equity={current_equity:.2f} | Size={event.bet_size:.2%} | "
                f"Suggestion: Increase bet size or use higher equity"
            )
            return

        logger.info(
            f"📊 Order calculation: Equity={current_equity:.2f} | "
            f"Size={event.bet_size:.2%} | Value={position_value:.2f} | "
            f"Price={current_price:.2f} | Amount={amount:.8f} (raw={amount_raw:.12f})"
        )

        order_payload = {
            "trade_id": trade_id,
            "symbol": event.symbol,
            "side": event.side,
            "size": event.bet_size,  # Fraction of equity
            "amount": amount,  # Calculated amount in contracts
            "take_profit": tp_pct,  # Pass as percentage (e.g. 0.01)
            "stop_loss": sl_pct,  # Pass as percentage (e.g. 0.01)
            "timestamp": str(event.timestamp),
            "ghost": False,
            "contributors": [getattr(event, "selected_sensor", "Unknown")],
        }

        # Store for outcome tracking (include sensor_id if available)
        sensor_id = getattr(event, "selected_sensor", "Unknown")
        self.pending_trades[trade_id] = (event, sensor_id)

        # Execute via Croupier with error handling
        from core.error_handling import RetryConfig, get_error_handler

        error_handler = get_error_handler()

        try:
            result = await error_handler.execute(
                self.croupier.execute_order,
                order_payload,
                retry_config=RetryConfig(
                    max_retries=3,
                    backoff_base=2.0,
                    backoff_max=30.0,
                ),
                context=f"execute_order_{event.symbol}",
            )

            # Check for success (support both simple orders and OCO bracket results)
            is_success = False
            if result.get("status") == "filled":
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
                # TODO: Track order to get outcome and update Paroli
            else:
                logger.warning(f"⚠️ Order Result: {result}")

        except Exception as e:
            logger.error(f"❌ Execution Failed after retries: {e}", exc_info=True)
            # Record failed order
            metrics.record_order_failed(
                exchange=self.croupier.exchange_adapter.connector.__class__.__name__.replace("NativeConnector", ""),
                reason=str(e)[:50],  # Truncate reason
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

        # LAYER 2 ATOMICITY PROTECTION: Conditional validation (only if errors occurred)
        # Check if Croupier flagged integrity issues
        if hasattr(self.croupier, "integrity_check_failed") and self.croupier.integrity_check_failed:
            self.validation_needed = True
            self.croupier.integrity_check_failed = False  # Reset Croupier flag
            logger.info("🚨 Integrity check failure detected, enabling conditional validation")

        if self.validation_needed:
            self.validation_candle_count += 1
            if self.validation_candle_count >= self.validation_interval:
                self.validation_candle_count = 0
                logger.info("🔍 Running conditional position integrity validation (triggered by previous errors)")
                try:
                    await self.croupier.validate_all_positions_integrity()
                    # Reset flag if validation succeeds
                    self.validation_needed = False
                    logger.info("✅ Validation complete, disabling periodic checks")
                except Exception as e:
                    logger.error(f"❌ Position validation failed: {e}", exc_info=True)
                    # Keep flag set to retry

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
