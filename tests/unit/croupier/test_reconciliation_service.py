import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.portfolio.position_tracker import OpenPosition, PositionTracker
from croupier.components.oco_manager import OCOManager
from croupier.components.reconciliation_service import ReconciliationService


class TestReconciliationService:
    @pytest.fixture
    def mock_adapter(self):
        adapter = MagicMock()
        adapter.fetch_order = AsyncMock()
        adapter.fetch_my_trades = AsyncMock(return_value=[])
        # Needed for force closing
        adapter.cancel_order = AsyncMock(return_value=True)
        adapter.execute_order = AsyncMock(return_value={"id": "close_123", "status": "closed"})
        return adapter

    @pytest.fixture
    def mock_tracker(self):
        tracker = MagicMock(spec=PositionTracker)
        tracker.open_positions = []
        tracker.remove_position = AsyncMock(return_value=True)
        tracker.finalize_removal = AsyncMock(return_value=True)
        tracker.lock_for_closure = AsyncMock(return_value=True)
        tracker.unlock = MagicMock()
        tracker.get_position = MagicMock(return_value=None)
        tracker.has_valid_bracket = MagicMock(return_value=(True, True))

        def mock_get_pos(trade_id):
            return next((p for p in tracker.open_positions if p.trade_id == trade_id), None)

        tracker.get_position.side_effect = mock_get_pos

        def mock_get_by_sym(sym):
            return [p for p in tracker.open_positions if p.symbol == sym]

        tracker.get_positions_by_symbol.side_effect = mock_get_by_sym

        return tracker

    @pytest.fixture
    def oco_manager(self):
        return MagicMock(spec=OCOManager)

    @pytest.fixture
    def recon_service(self, mock_adapter, mock_tracker, oco_manager):
        service = ReconciliationService(mock_adapter, mock_tracker, oco_manager)
        # Mocking error_handler directly to avoid actual circuit breakers in tests
        service.error_handler = MagicMock()
        service.error_handler.execute_with_breaker = AsyncMock(
            side_effect=lambda name, func, *args, **kwargs: func(*args)
        )
        service.error_handler.shutdown_mode = False
        return service

    @pytest.mark.asyncio
    async def test_ghost_order_cleanup(self, recon_service, mock_tracker, mock_adapter):
        """Test that a ghost order without a valid grace period gets cleaned up."""
        # Create a ghost position (in local tracker but NOT on exchange)
        # Make entry timestamp old enough to bypass the 120s grace period
        old_time = (time.time() - 300) * 1000
        ghost_pos = OpenPosition(
            trade_id="ghost_1",
            symbol="BTC/USDT",
            side="LONG",
            entry_price=50000.0,
            amount=1.0,
            entry_timestamp=str(old_time),
            status="OPEN",
            timestamp=old_time / 1000.0,
            margin_used=10.0,
            notional=50000.0,
            leverage=5.0,
            tp_level=55000.0,
            sl_level=45000.0,
            order={"amount": 1.0},
        )
        mock_tracker.open_positions.append(ghost_pos)
        mock_tracker.get_position.side_effect = lambda tid: ghost_pos if tid == "ghost_1" else None
        mock_tracker.get_positions_by_symbol.return_value = [ghost_pos]

        # Simulate exchange having 0 positions for this symbol
        exchange_positions = []
        open_orders = []

        # Make investigate_ghost inconclusive (e.g. no TP/SL filled)
        recon_service._investigate_ghost = AsyncMock(return_value=None)
        recon_service.oco_manager = None  # Disable smart healing
        mock_tracker.has_valid_bracket.return_value = (False, False)

        report = await recon_service._reconcile_symbol_data("BTC/USDT", exchange_positions, open_orders)

        assert report["ghosts_removed"] == 1, f"Report was: {report}"
        mock_tracker.remove_position.assert_called_with("ghost_1")

    @pytest.mark.asyncio
    async def test_inflight_grace_period(self, recon_service, mock_tracker):
        """Test that a recently created position is not removed even if it's missing from the exchange."""
        # Create a new position well within the 120s grace period
        recent_time = (time.time() - 10) * 1000
        new_pos = OpenPosition(
            trade_id="CASINO_ENTRY_1",
            symbol="BTC/USDT",
            side="LONG",
            entry_price=50000.0,
            amount=1.0,
            entry_timestamp=str(recent_time),
            status="OPEN",
            timestamp=recent_time / 1000.0,
            margin_used=10.0,
            notional=50000.0,
            leverage=5.0,
            tp_level=55000.0,
            sl_level=45000.0,
            order={"amount": 1.0},
        )
        mock_tracker.open_positions.append(new_pos)
        mock_tracker.get_position.side_effect = lambda tid: new_pos if tid == "CASINO_ENTRY_1" else None
        mock_tracker.get_positions_by_symbol.return_value = [new_pos]

        exchange_positions = []
        open_orders = []

        report = await recon_service._reconcile_symbol_data("BTC/USDT", exchange_positions, open_orders)

        # Should NOT be removed as ghost due to grace period
        assert report["ghosts_removed"] == 0
        mock_tracker.remove_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_position_sync_recovery(self, recon_service, mock_tracker):
        """Test adopting an unknown healthy position from the exchange."""
        exchange_positions = [
            {
                "symbol": "BTC/USDT",
                "side": "long",
                "contracts": 1.0,
                "entryPrice": 50000.0,
            }
        ]
        # Open orders correctly tagged for semantic adoption
        open_orders = [
            {"clientOrderId": "C3_TP_test1", "side": "sell", "type": "LIMIT", "price": 51000.0},
            {"clientOrderId": "C3_SL_test1", "side": "sell", "type": "STOP_MARKET", "stopPrice": 49000.0},
        ]

        mock_tracker.add_position = MagicMock()
        mock_tracker.register_alias = MagicMock()

        # Make sure the tracker has no local positions
        mock_tracker.open_positions = []

        # We need to mock _cleanup_orphaned_orders to avoid actual API calls in the test
        recon_service._cleanup_orphaned_orders = AsyncMock(return_value=0)

        report = await recon_service._reconcile_symbol_data("BTC/USDT", exchange_positions, open_orders)

        assert report["positions_fixed"] == 1
        mock_tracker.add_position.assert_called_once()

        # Verify the adopted position
        adopted_pos = mock_tracker.add_position.call_args[0][0]
        assert "adopted" in adopted_pos.trade_id
        assert adopted_pos.symbol == "BTC/USDT"
        assert adopted_pos.side == "LONG"
        assert adopted_pos.tp_level == 51000.0
        assert adopted_pos.sl_level == 49000.0
