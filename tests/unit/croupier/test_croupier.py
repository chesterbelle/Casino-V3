"""
Unit tests for Croupier orchestrator.

Tests the main Croupier facade that coordinates OrderExecutor,
OCOManager, and ReconciliationService.
"""

from unittest.mock import AsyncMock

import pytest

from core.portfolio.position_tracker import OpenPosition
from croupier.croupier import Croupier


class TestCroupier:
    """Test suite for Croupier orchestrator."""

    @pytest.fixture
    def mock_adapter(self):
        """Create mock exchange adapter."""
        adapter = AsyncMock()
        adapter.connector = AsyncMock()
        return adapter

    @pytest.fixture
    def croupier(self, mock_adapter):
        """Create Croupier instance."""
        return Croupier(exchange_adapter=mock_adapter, initial_balance=10000.0, max_concurrent_positions=5)

    def test_croupier_initialization(self, croupier):
        """Test Croupier initializes all components correctly."""
        # Assert components are initialized
        assert croupier.order_executor is not None
        assert croupier.oco_manager is not None
        assert croupier.reconciliation is not None
        assert croupier.balance_manager is not None
        assert croupier.position_tracker is not None
        assert croupier.error_handler is not None

        # Assert balance initialized correctly
        assert croupier.get_balance() == 10000.0

    @pytest.mark.asyncio
    async def test_execute_order_delegates_to_oco_manager(self, croupier):
        """Test execute_order delegates to OCOManager."""
        # Arrange
        order = {
            "symbol": "BTC/USDT:USDT",
            "side": "LONG",
            "amount": 0.001,
            "take_profit": 1.01,
            "stop_loss": 0.99,
            "margin_used": 100.0,
            "notional": 50.0,
            "leverage": 1,
        }

        # Mock OCOManager response
        oco_result = {
            "main_order": {"order_id": "main_123", "timestamp": "2024-01-01T00:00:00Z"},
            "tp_order": {"order_id": "tp_456"},
            "sl_order": {"order_id": "sl_789"},
            "fill_price": 50000.0,
            "tp_price": 50500.0,
            "sl_price": 49500.0,
        }
        croupier.oco_manager.create_bracketed_order = AsyncMock(return_value=oco_result)

        # Act
        result = await croupier.execute_order(order)

        # Assert
        assert result == oco_result
        croupier.oco_manager.create_bracketed_order.assert_called_once_with(order, wait_for_fill=True)

        # Verify position was registered
        assert len(croupier.get_open_positions()) == 1
        position = croupier.get_open_positions()[0]
        assert position.trade_id == "main_123"
        assert position.symbol == "BTC/USDT:USDT"
        assert position.entry_price == 50000.0

    @pytest.mark.asyncio
    async def test_reconcile_positions_single_symbol(self, croupier):
        """Test reconciliation for a single symbol."""
        # Arrange
        symbol = "BTC/USDT:USDT"
        expected_report = {
            "symbol": symbol,
            "positions_checked": 1,
            "positions_fixed": 0,
            "positions_closed": 0,
            "orders_cancelled": 0,
            "issues_found": [],
        }

        croupier.reconciliation.reconcile_symbol = AsyncMock(return_value=expected_report)

        # Act
        result = await croupier.reconcile_positions(symbol)

        # Assert
        assert result == expected_report
        croupier.reconciliation.reconcile_symbol.assert_called_once_with(symbol)

    @pytest.mark.asyncio
    async def test_reconcile_positions_all_symbols(self, croupier):
        """Test reconciliation for all open positions."""
        # Arrange - Add some positions
        position1 = OpenPosition(
            trade_id="1",
            symbol="BTC/USDT:USDT",
            side="LONG",
            entry_price=50000.0,
            entry_timestamp="2024-01-01T00:00:00Z",
            margin_used=100.0,
            notional=50.0,
            leverage=1,
            tp_level=50500.0,
            sl_level=49500.0,
            main_order_id="main_1",
            tp_order_id="tp_1",
            sl_order_id="sl_1",
        )
        position2 = OpenPosition(
            trade_id="2",
            symbol="ETH/USDT:USDT",
            side="SHORT",
            entry_price=3000.0,
            entry_timestamp="2024-01-01T00:00:00Z",
            margin_used=50.0,
            notional=30.0,
            leverage=1,
            tp_level=2970.0,
            sl_level=3030.0,
            main_order_id="main_2",
            tp_order_id="tp_2",
            sl_order_id="sl_2",
        )

        croupier.position_tracker.open_positions = [position1, position2]

        report1 = {"symbol": "BTC/USDT:USDT", "positions_checked": 1}
        report2 = {"symbol": "ETH/USDT:USDT", "positions_checked": 1}

        croupier.reconciliation.reconcile_symbol = AsyncMock(side_effect=[report1, report2])

        # Act
        results = await croupier.reconcile_positions()  # No symbol = all

        # Assert
        assert len(results) == 2
        assert croupier.reconciliation.reconcile_symbol.call_count == 2

    def test_get_balance(self, croupier):
        """Test getting current balance."""
        assert croupier.get_balance() == 10000.0

    def test_get_equity(self, croupier):
        """Test getting current equity."""
        # Initially, equity equals balance when no positions
        assert croupier.get_equity() == 10000.0

    def test_get_open_positions(self, croupier):
        """Test getting open positions."""
        assert croupier.get_open_positions() == []

    def test_can_open_position(self, croupier):
        """Test checking if position can be opened."""
        # With 10000 balance, should be able to open position with 100 margin
        assert croupier.can_open_position(100.0) is True

        # Should not be able to open position with 20000 margin
        assert croupier.can_open_position(20000.0) is False

    def test_get_stats(self, croupier):
        """Test getting trading statistics."""
        stats = croupier.get_stats()
        assert isinstance(stats, dict)

    def test_repr(self, croupier):
        """Test string representation."""
        repr_str = repr(croupier)
        assert "Croupier" in repr_str
        assert "balance=10000.00" in repr_str
        assert "positions=0" in repr_str
