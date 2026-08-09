"""
Unit tests for OrderExecutor.

Tests the order execution component with ErrorHandler integration,
retry logic, and validation.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.exceptions import ValidationError
from croupier.components.order_executor import OrderExecutor


class TestOrderExecutor:
    """Test suite for OrderExecutor."""

    @pytest.fixture
    def mock_adapter(self):
        """Create mock exchange adapter."""
        adapter = AsyncMock()
        adapter.execute_order = AsyncMock()
        adapter.get_current_price = AsyncMock(return_value=50000.0)
        adapter.get_min_notional = Mock(return_value=10.0)
        adapter.amount_to_precision = Mock(side_effect=lambda symbol, val: val)
        adapter.price_to_precision = Mock(side_effect=lambda symbol, val: val)
        adapter.is_congested = False
        return adapter

    @pytest.fixture
    def mock_error_handler(self):
        """Create mock error handler."""
        handler = Mock()
        handler.execute_with_breaker = AsyncMock()
        return handler

    @pytest.fixture
    def executor(self, mock_adapter, mock_error_handler):
        """Create OrderExecutor instance."""
        return OrderExecutor(mock_adapter, mock_error_handler)

    @pytest.mark.asyncio
    async def test_execute_market_order_success(self, executor, mock_error_handler):
        """Test successful market order execution."""
        # Arrange
        order = {"symbol": "BTC/USDT", "side": "BUY", "amount": 0.01}
        expected_result = {"order_id": "123", "status": "filled", "average": 50000.0}

        # Mock error_handler.execute_with_breaker to call the function directly
        async def mock_execute_with_breaker(breaker_name, func, *args, **kwargs):
            return await func(*args)

        mock_error_handler.execute_with_breaker.side_effect = mock_execute_with_breaker
        executor.adapter.execute_order.return_value = expected_result

        # Act
        result = await executor.execute_market_order(order)

        # Assert
        assert result == expected_result
        mock_error_handler.execute_with_breaker.assert_called_once()
        executor.adapter.execute_order.assert_called_once_with(order)

    @pytest.mark.asyncio
    async def test_execute_market_order_validation_error(self, executor):
        """Test market order with invalid parameters."""
        # Arrange
        invalid_order = {"symbol": "BTC/USDT", "side": "BUY"}  # Missing amount

        # Act & Assert
        with pytest.raises(ValueError, match="Missing required field: amount"):
            await executor.execute_market_order(invalid_order)

    @pytest.mark.asyncio
    async def test_execute_market_order_invalid_amount(self, executor):
        """Test market order with invalid amount."""
        # Arrange
        order = {"symbol": "BTC/USDT", "side": "BUY", "amount": -0.01}

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid amount"):
            await executor.execute_market_order(order)

    @pytest.mark.asyncio
    async def test_execute_market_order_invalid_side(self, executor):
        """Test market order with invalid side."""
        # Arrange
        order = {"symbol": "BTC/USDT", "side": "INVALID", "amount": 0.01}

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid side"):
            await executor.execute_market_order(order)

    @pytest.mark.asyncio
    async def test_execute_limit_order_success(self, executor, mock_error_handler):
        """Test successful limit order execution."""
        # Arrange
        expected_result = {"order_id": "456", "status": "open"}

        async def mock_execute_with_breaker(breaker_name, func, *args, **kwargs):
            return await func(*args)

        mock_error_handler.execute_with_breaker.side_effect = mock_execute_with_breaker
        executor.adapter.execute_order.return_value = expected_result

        # Act
        result = await executor.execute_limit_order(symbol="BTC/USDT", side="BUY", amount=0.01, price=50000.0)

        # Assert
        assert result == expected_result
        assert executor.adapter.execute_order.called

    @pytest.mark.asyncio
    async def test_execute_limit_order_invalid_price(self, executor):
        """Test limit order with invalid price."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid price"):
            await executor.execute_limit_order(symbol="BTC/USDT", side="BUY", amount=0.01, price=-100.0)

    @pytest.mark.asyncio
    async def test_execute_stop_order_success(self, executor, mock_error_handler):
        """Test successful stop order execution."""
        # Arrange
        expected_result = {"order_id": "789", "status": "pending"}

        async def mock_execute_with_breaker(breaker_name, func, *args, **kwargs):
            return await func(*args)

        mock_error_handler.execute_with_breaker.side_effect = mock_execute_with_breaker
        executor.adapter.execute_order.return_value = expected_result

        # Act
        result = await executor.execute_stop_order(symbol="BTC/USDT", side="SELL", amount=0.01, stop_price=49000.0)

        # Assert
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_execute_stop_order_invalid_stop_price(self, executor):
        """Test stop order with invalid stop price."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid stopPrice"):
            await executor.execute_stop_order(symbol="BTC/USDT", side="SELL", amount=0.01, stop_price=0)

    @pytest.mark.asyncio
    async def test_validate_market_order_missing_fields(self, executor):
        """Test validation catches missing required fields."""
        # Test missing symbol
        with pytest.raises(ValueError, match="Missing required field: symbol"):
            executor._validate_market_order({"side": "BUY", "amount": 0.01})

        # Test missing side
        with pytest.raises(ValueError, match="Missing required field: side"):
            executor._validate_market_order({"symbol": "BTC/USDT", "amount": 0.01})

        # Test missing amount
        with pytest.raises(ValueError, match="Missing required field: amount"):
            executor._validate_market_order({"symbol": "BTC/USDT", "side": "BUY"})

    def test_validate_market_order_success(self, executor):
        """Test validation passes for valid order."""
        # This should not raise
        executor._validate_market_order({"symbol": "BTC/USDT", "side": "BUY", "amount": 0.01})

    def test_validate_limit_order_success(self, executor):
        """Test validation passes for valid limit order."""
        # This should not raise
        executor._validate_limit_order({"symbol": "BTC/USDT", "side": "BUY", "amount": 0.01, "price": 50000.0})

    def test_validate_stop_order_success(self, executor):
        """Test validation passes for valid stop order."""
        # This should not raise
        executor._validate_stop_order({"symbol": "BTC/USDT", "side": "SELL", "amount": 0.01, "stop_price": 49000.0})


# ============================================================
# Tests for Pre-Entry Notional Validation (Phase 250+)
# ============================================================


class TestPreEntryNotionalValidation:
    """Test suite for pre-entry notional validation."""

    @pytest.fixture
    def mock_adapter(self):
        """Create mock exchange adapter."""
        adapter = AsyncMock()
        adapter.execute_order = AsyncMock()
        adapter.get_current_price = AsyncMock(return_value=50000.0)
        adapter.get_min_notional = Mock(return_value=10.0)
        adapter.amount_to_precision = Mock(side_effect=lambda symbol, val: val)
        adapter.price_to_precision = Mock(side_effect=lambda symbol, val: val)
        adapter.is_congested = False
        return adapter

    @pytest.fixture
    def mock_error_handler(self):
        """Create mock error handler."""
        handler = Mock()
        handler.execute_with_breaker = AsyncMock()
        return handler

    @pytest.fixture
    def executor(self, mock_adapter, mock_error_handler):
        """Create OrderExecutor instance."""
        return OrderExecutor(mock_adapter, mock_error_handler)

    @pytest.mark.asyncio
    async def test_pre_entry_rejects_below_min_notional(self, executor):
        """Test that entries below min notional are rejected."""
        order = {"symbol": "BTC/USDT", "side": "BUY", "amount": 0.0001}  # Very small amount
        # min_notional = 10.0, current_price = 50000.0
        # projected_notional = 0.0001 * 50000.0 = 5.0 < 10.0

        with pytest.raises(ValidationError, match="notional.*< min"):
            await executor.execute_market_order(order)

    @pytest.mark.asyncio
    async def test_pre_entry_allows_above_min_notional(self, executor, mock_error_handler):
        """Test that entries above min notional are allowed."""
        order = {"symbol": "BTC/USDT", "side": "BUY", "amount": 0.01}  # 0.01 * 50000 = 500 > 10
        expected_result = {"order_id": "123", "status": "filled", "average": 50000.0}

        async def mock_execute_with_breaker(breaker_name, func, *args, **kwargs):
            return await func(*args)

        mock_error_handler.execute_with_breaker.side_effect = mock_execute_with_breaker
        executor.adapter.execute_order.return_value = expected_result

        result = await executor.execute_market_order(order)
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_pre_entry_skips_reduce_only(self, executor, mock_error_handler):
        """Test that reduceOnly orders skip notional validation."""
        order = {"symbol": "BTC/USDT", "side": "SELL", "amount": 0.0001, "params": {"reduceOnly": True}}
        expected_result = {"order_id": "123", "status": "filled", "average": 50000.0}

        async def mock_execute_with_breaker(breaker_name, func, *args, **kwargs):
            return await func(*args)

        mock_error_handler.execute_with_breaker.side_effect = mock_execute_with_breaker
        executor.adapter.execute_order.return_value = expected_result

        # Should not raise ValidationError even though notional is small
        result = await executor.execute_market_order(order)
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_pre_entry_skips_close_position(self, executor, mock_error_handler):
        """Test that closePosition orders skip notional validation."""
        order = {"symbol": "BTC/USDT", "side": "SELL", "amount": 0, "params": {"closePosition": True}}
        expected_result = {"order_id": "123", "status": "filled", "average": 50000.0}

        async def mock_execute_with_breaker(breaker_name, func, *args, **kwargs):
            return await func(*args)

        mock_error_handler.execute_with_breaker.side_effect = mock_execute_with_breaker
        executor.adapter.execute_order.return_value = expected_result

        # Should not raise ValidationError even though amount is 0
        result = await executor.execute_market_order(order)
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_pre_entry_handles_adapter_error_gracefully(self, executor, mock_error_handler):
        """Test that adapter errors during notional check are handled gracefully."""
        order = {"symbol": "BTC/USDT", "side": "BUY", "amount": 0.01}
        expected_result = {"order_id": "123", "status": "filled", "average": 50000.0}

        # Make get_current_price raise an exception
        executor.adapter.get_current_price = AsyncMock(side_effect=Exception("API down"))

        async def mock_execute_with_breaker(breaker_name, func, *args, **kwargs):
            return await func(*args)

        mock_error_handler.execute_with_breaker.side_effect = mock_execute_with_breaker
        executor.adapter.execute_order.return_value = expected_result

        # Should proceed despite the error (with warning log)
        result = await executor.execute_market_order(order)
        assert result == expected_result
