"""
Regression tests for OCOManager small-notional brackets (Hallazgo #8).

Validates that TP/SL brackets with notional < min_notional use
real quantity + reduceOnly (never closePosition=True, which Binance
rejects with -4120 on the Main API for conditional orders).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from croupier.components.oco_manager import OCOManager


class TestSmallNotionalBrackets:
    """Small-notional TP/SL must not use closePosition=True."""

    @pytest.fixture
    def manager(self):
        manager = OCOManager.__new__(OCOManager)
        manager.logger = MagicMock()
        manager.adapter = MagicMock()
        manager.adapter.connector = MagicMock()
        manager.adapter.connector.get_min_notional = MagicMock(return_value=20.0)
        manager.adapter.get_current_price = AsyncMock(return_value=75.5)
        manager.adapter.connector.get_tick_size = MagicMock(return_value=0.01)
        manager.executor = MagicMock()
        manager.executor.execute_stop_order = AsyncMock(
            return_value={"id": "algo1", "status": "new", "amount": 0.19, "price": 0.0}
        )
        manager.error_handler = MagicMock()

        async def _run_breaker(_name, func, **_kw):
            return await func()

        manager.error_handler.execute_with_breaker = AsyncMock(side_effect=_run_breaker)
        manager.tpsl_retry_config = {}
        return manager

    @pytest.mark.asyncio
    async def test_tp_small_notional_uses_reduce_only_with_real_amount(self, manager):
        """TP below min notional: real amount + reduceOnly, never closePosition."""
        await manager._create_tp_order(
            symbol="SOLUSDT",
            side="SHORT",
            amount=0.1928,
            tp_price=75.03,
        )

        args, kwargs = manager.executor.execute_stop_order.await_args
        assert kwargs["amount"] == 0.1928  # real amount, not 0
        assert kwargs["order_type"] == "TAKE_PROFIT_MARKET"
        assert kwargs["params"]["reduceOnly"] is True
        assert "closePosition" not in kwargs["params"]
        assert kwargs["params"]["workingType"] == "MARK_PRICE"

    @pytest.mark.asyncio
    async def test_sl_small_notional_uses_reduce_only_with_real_amount(self, manager):
        """SL below min notional: real amount + reduceOnly, never closePosition."""
        await manager._create_sl_order(
            symbol="SOLUSDT",
            side="SHORT",
            amount=0.1928,
            sl_price=76.0,
        )

        args, kwargs = manager.executor.execute_stop_order.await_args
        assert kwargs["amount"] == 0.1928  # real amount, not 0
        assert kwargs["params"]["reduceOnly"] is True
        assert "closePosition" not in kwargs["params"]

    @pytest.mark.asyncio
    async def test_tp_normal_notional_unchanged(self, manager):
        """Normal notional TP keeps its existing reduceOnly path."""
        await manager._create_tp_order(
            symbol="SOLUSDT",
            side="SHORT",
            amount=2.0,
            tp_price=75.03,
        )

        args, kwargs = manager.executor.execute_stop_order.await_args
        assert kwargs["amount"] == 2.0
        assert kwargs["params"]["reduceOnly"] is True
        assert "closePosition" not in kwargs["params"]
