"""
Execution Layer for Casino-V3.
Handles trade lifecycle: candle-based exits, reconciliation, and closure tracking.
"""

import logging

from core.events import EventType, TradeClosedEvent
from croupier.croupier import Croupier

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages trade lifecycle: startup reconciliation, candle-based exits, and closure tracking.
    """

    def __init__(self, engine, croupier: Croupier):
        self.engine = engine
        self.croupier = croupier
        self.active = False

        # Subscribe to CANDLE events to check for TP/SL exits
        self.engine.subscribe(EventType.CANDLE, self.on_candle)

        # Subscribe to TRADE_CLOSED events to update execution state
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

    async def on_trade_closed(self, event: TradeClosedEvent):
        """Handle unified trade closure event."""
        logger.info(
            f"📊 Trade Closed: {event.trade_id} | {event.exit_reason} | Won: {event.won} | PnL: {event.pnl:.2f}"
        )

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
            "timeframe": "1m",
        }

        # Check for potential exits (TP/SL touched via candle analysis)
        potential_exits = self.croupier.position_tracker.check_and_close_positions(candle_dict)

        # Determine execution mode
        mode = "testing"
        try:
            if hasattr(self.croupier.exchange_adapter, "connector"):
                connector = self.croupier.exchange_adapter.connector
                mode = getattr(connector, "mode", "testing")
        except Exception:
            pass

        for exit_info in potential_exits:
            trade_id = exit_info["trade_id"]
            exit_reason = exit_info["exit_reason_detected"]

            # Internal Exits (TIME, MANUAL) are executed by OrderManager
            if exit_reason in ["TIME_EXIT", "MANUAL_SYNC", "FORCE_CLOSE"]:
                logger.info(f"⏳ Executing {exit_reason} for {trade_id} in {mode} mode")
                try:
                    await self.croupier.close_position(trade_id)
                    logger.info(f"✅ {exit_reason} executed successfully for {trade_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to execute {exit_reason} for {trade_id}: {e}")

            # Exchange Exits (TP, SL, LIQUIDATION) delegated to exchange engine
            elif exit_reason in ["TP", "SL", "LIQUIDATION"]:
                continue
