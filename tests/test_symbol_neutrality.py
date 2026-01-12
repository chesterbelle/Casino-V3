import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# MOCK FAIL-SAFE: Ensure dependencies are available for import
try:
    import aiolimiter  # noqa: F401
except ImportError:
    sys.modules["aiolimiter"] = MagicMock()
    sys.modules["aiolimiter"].AsyncLimiter = MagicMock()

try:
    import eth_account  # noqa: F401
except ImportError:
    sys.modules["eth_account"] = MagicMock()
    sys.modules["eth_account"].Account = MagicMock()

try:
    import hyperliquid  # noqa: F401
except ImportError:
    mock_hl = MagicMock()
    sys.modules["hyperliquid"] = mock_hl
    sys.modules["hyperliquid.exchange"] = MagicMock()
    sys.modules["hyperliquid.utils"] = MagicMock()

from core.events import CandleEvent, EventType
from core.portfolio.position_tracker import OpenPosition, PositionTracker
from croupier.components.reconciliation_service import ReconciliationService


class TestSymbolNeutrality(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tracker = PositionTracker(max_concurrent_positions=10)
        self.adapter = MagicMock()
        # Mock async methods
        self.adapter.fetch_order = AsyncMock()
        self.adapter.fetch_positions = AsyncMock()
        self.adapter.fetch_open_orders = AsyncMock()
        self.adapter.create_market_order = AsyncMock()
        self.adapter.get_current_price = AsyncMock()

        self.oco_manager = MagicMock()
        self.reconciliation = ReconciliationService(self.adapter, self.tracker, self.oco_manager)

    async def test_position_normalization_on_open(self):
        """Verify that positions are stored with normalized symbols regardless of input."""
        order = {"symbol": "ATOM/USDT:USDT", "side": "LONG", "size": 0.05, "leverage": 1.0}
        pos = self.tracker.open_position(
            order=order, entry_price=10.0, entry_timestamp="123456789", available_equity=1000.0
        )
        self.assertEqual(pos.symbol, "ATOMUSDT")
        self.assertEqual(self.tracker.open_positions[0].symbol, "ATOMUSDT")

    async def test_reconciliation_symbol_neutrality(self):
        """Verify that reconciliation matches ATOMUSDT (local) with ATOM/USDT:USDT (exchange)."""
        # 1. Setup local position (already normalized per fix above)
        order = {"symbol": "ATOM/USDT", "side": "LONG", "size": 0.05, "leverage": 1.0}
        pos = self.tracker.open_position(
            order=order,
            entry_price=10.0,
            entry_timestamp="123456789",
            available_equity=1000.0,
            tp_order_id="1",  # Use simple ID that matches exchange mock
            sl_order_id="2",
        )
        # Mock order objects with recent timestamps to avoid grace period issues
        now = time.time()
        pos.tp_order = MagicMock(client_order_id="C3_TP_1", last_updated=now)
        pos.sl_order = MagicMock(client_order_id="C3_SL_1", last_updated=now)

        # 2. Mock exchange reporting the RAW symbol
        exchange_positions = [{"symbol": "ATOM/USDT:USDT", "contracts": 5.0, "entryPrice": 10.0, "side": "long"}]
        open_orders = [
            {
                "id": "1",
                "clientOrderId": "C3_TP_1",
                "symbol": "ATOM/USDT:USDT",
                "status": "open",
                "type": "LIMIT",
                "side": "sell",
                "price": 11.0,
            },
            {
                "id": "2",
                "clientOrderId": "C3_SL_1",
                "symbol": "ATOM/USDT:USDT",
                "status": "open",
                "type": "STOP_MARKET",
                "side": "sell",
                "stopPrice": 9.0,
            },
        ]

        # 3. Run reconciliation
        # Note: We call _reconcile_symbol_data which is the core logic
        report = await self.reconciliation._reconcile_symbol_data("ATOMUSDT", exchange_positions, open_orders)

        # 4. Verify no ghosts were removed and position remains active
        self.assertEqual(report["ghosts_removed"], 0)
        self.assertEqual(report["positions_closed"], 0)
        self.assertEqual(len(self.tracker.open_positions), 1)
        self.assertEqual(self.tracker.open_positions[0].symbol, "ATOMUSDT")

    async def test_exit_manager_matching(self):
        """Verify ExitManager matches ATOMUSDT position with ATOM/USDT:USDT candle."""
        from croupier.components.exit_manager import ExitManager

        croupier = MagicMock()
        croupier.get_open_positions.return_value = [
            OpenPosition(
                trade_id="t1",
                symbol="ATOMUSDT",
                side="LONG",
                entry_price=10.0,
                entry_timestamp="0",
                margin_used=10.0,
                notional=10.0,
                leverage=1.0,
                tp_level=12.0,
                sl_level=8.0,
                liquidation_level=5.0,
                order={},
            )
        ]

        exit_mgr = ExitManager(croupier)

        # Mock candle with RAW symbol
        # CandleEvent(type, timestamp, symbol, timeframe, open, high, low, close, volume)
        candle = CandleEvent(
            type=EventType.CANDLE,
            timestamp=123.456,
            symbol="ATOM/USDT:USDT",
            timeframe="15m",
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.1,
            volume=100.0,
        )

        # We check if processing logic is reached
        with patch.object(exit_mgr, "logger") as mock_logger:
            await exit_mgr.on_candle(candle)
            # Find if "Processing Exit Logic for ATOMUSDT" was logged
            found = any(
                "Processing Exit Logic for ATOMUSDT" in (call.args[0] if call.args else "")
                for call in mock_logger.info.call_args_list
            )
            self.assertTrue(found, "Exit logic was not processed for normalized symbol")


if __name__ == "__main__":
    unittest.main()
