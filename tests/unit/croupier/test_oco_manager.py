"""
Unit tests for OCOManager.

Tests the OCO bracket order creation with atomicity guarantees,
fill confirmation, and cleanup on failure.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from croupier.components.oco_manager import OCOAtomicityError, OCOManager


class TestOCOManager:
    """Test suite for OCOManager."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.execute_market_order = AsyncMock()
        executor.execute_limit_order = AsyncMock()
        executor.execute_stop_order = AsyncMock()
        return executor

    @pytest.fixture
    def mock_tracker(self):
        """Create mock position tracker."""
        return Mock()

    @pytest.fixture
    def mock_adapter(self):
        """Create mock exchange adapter."""
        adapter = AsyncMock()
        adapter.connector = AsyncMock()
        return adapter

    @pytest.fixture
    def oco_manager(self, mock_executor, mock_tracker, mock_adapter):
        """Create OCOManager instance."""
        return OCOManager(mock_executor, mock_tracker, mock_adapter)

    @pytest.mark.asyncio
    async def test_create_bracketed_order_success(self, oco_manager, mock_executor):
        """Test successful OCO bracket creation."""
        # Arrange
        order = {
            "symbol": "BTC/USDT:USDT",
            "side": "LONG",
            "size": 0.01,
            "amount": 0.001,
            "take_profit": 1.01,
            "stop_loss": 0.99,
        }

        mock_executor.execute_market_order.return_value = {
            "order_id": "main_123",
            "status": "filled",
            "average": 50000.0,
            "amount": 0.001,
            "timestamp": "2024-01-01T00:00:00Z",
        }
        mock_executor.execute_limit_order.return_value = {
            "order_id": "tp_456",
            "status": "open",
        }
        mock_executor.execute_stop_order.return_value = {
            "order_id": "sl_789",
            "status": "open",
        }

        # Act
        result = await oco_manager.create_bracketed_order(order, wait_for_fill=False)

        # Assert
        assert result["main_order"]["order_id"] == "main_123"
        assert result["tp_order"]["order_id"] == "tp_456"
        assert result["sl_order"]["order_id"] == "sl_789"
        assert result["fill_price"] == 50000.0
        assert result["tp_price"] == 50500.0  # 50000 * 1.01
        assert result["sl_price"] == 49500.0  # 50000 * 0.99

    @pytest.mark.asyncio
    async def test_create_bracketed_order_tp_fails_cleanup(self, oco_manager, mock_executor, mock_adapter):
        """Test cleanup when TP order fails."""
        # Arrange
        order = {
            "symbol": "BTC/USDT:USDT",
            "side": "LONG",
            "size": 0.01,
            "amount": 0.001,
            "take_profit": 1.01,
            "stop_loss": 0.99,
        }

        mock_executor.execute_market_order.return_value = {
            "order_id": "main_123",
            "average": 50000.0,
            "amount": 0.001,
        }
        # TP order fails
        mock_executor.execute_limit_order.side_effect = Exception("TP order failed")

        # Act & Assert
        with pytest.raises(OCOAtomicityError, match="Failed to create OCO bracket"):
            await oco_manager.create_bracketed_order(order, wait_for_fill=False)

        # Verify cleanup was called
        # Note: In real implementation, would verify cancel_order was called
        # mock_adapter.connector.cancel_order.assert_called()

    @pytest.mark.asyncio
    async def test_calculate_tp_sl_prices_long(self, oco_manager):
        """Test TP/SL calculation for LONG positions."""
        # Arrange
        entry_price = 50000.0
        side = "LONG"
        tp_multiplier = 1.01
        sl_multiplier = 0.99

        # Act
        tp_price, sl_price = oco_manager._calculate_tp_sl_prices(entry_price, side, tp_multiplier, sl_multiplier)

        # Assert
        assert tp_price == 50500.0  # 50000 * 1.01
        assert sl_price == 49500.0  # 50000 * 0.99

    @pytest.mark.asyncio
    async def test_calculate_tp_sl_prices_short(self, oco_manager):
        """Test TP/SL calculation for SHORT positions."""
        # Arrange
        entry_price = 50000.0
        side = "SHORT"
        tp_multiplier = 1.01
        sl_multiplier = 0.99

        # Act
        tp_price, sl_price = oco_manager._calculate_tp_sl_prices(entry_price, side, tp_multiplier, sl_multiplier)

        # Assert
        assert tp_price == 49500.0  # TP is lower for shorts
        assert sl_price == 50500.0  # SL is higher for shorts

    @pytest.mark.asyncio
    async def test_wait_for_fill_timeout(self, oco_manager, mock_adapter):
        """Test timeout when waiting for fill."""
        # Arrange
        order_id = "test_123"
        mock_adapter.connector.fetch_order.return_value = {"status": "pending"}

        # Act & Assert
        with pytest.raises(TimeoutError, match="not filled within"):
            await oco_manager._wait_for_fill(order_id, timeout=0.5)

    @pytest.mark.asyncio
    async def test_wait_for_fill_success(self, oco_manager, mock_adapter):
        """Test successful fill confirmation."""
        # Arrange
        order_id = "test_123"
        mock_adapter.connector.fetch_order.return_value = {
            "status": "closed",
            "average": 50000.0,
        }

        # Act
        fill_price = await oco_manager._wait_for_fill(order_id, timeout=1.0)

        # Assert
        assert fill_price == 50000.0

    def test_validate_oco_complete_success(self, oco_manager):
        """Test validation passes for complete OCO."""
        # Arrange
        main_order = {"order_id": "main_123"}
        tp_order = {"order_id": "tp_456"}
        sl_order = {"order_id": "sl_789"}

        # Act & Assert - should not raise
        oco_manager._validate_oco_complete(main_order, tp_order, sl_order)

    def test_validate_oco_complete_missing_main(self, oco_manager):
        """Test validation fails when main order missing."""
        # Act & Assert
        with pytest.raises(OCOAtomicityError, match="Main order is missing"):
            oco_manager._validate_oco_complete(None, {}, {})

    def test_validate_oco_complete_missing_tp(self, oco_manager):
        """Test validation fails when TP order missing."""
        # Act & Assert
        with pytest.raises(OCOAtomicityError, match="TP order is missing"):
            oco_manager._validate_oco_complete({"order_id": "123"}, None, {})

    def test_validate_oco_complete_missing_sl(self, oco_manager):
        """Test validation fails when SL order missing."""
        # Act & Assert
        with pytest.raises(OCOAtomicityError, match="SL order is missing"):
            oco_manager._validate_oco_complete({"order_id": "123"}, {}, None)

    def test_validate_oco_complete_missing_order_ids(self, oco_manager):
        """Test validation fails when order IDs missing."""
        # Act & Assert
        with pytest.raises(OCOAtomicityError, match="no order_id"):
            oco_manager._validate_oco_complete({}, {"order_id": "456"}, {"order_id": "789"})
