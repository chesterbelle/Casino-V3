"""
Regression tests for Hallazgo #10 (Smart Healing NameError fix).

Validates the Phase 262 design rule:
  - restore_bracket must resolve the position quantity BEFORE restoring
    TP/SL legs. Previously it referenced an undefined `amount` variable,
    crashing Smart Healing with `NameError: name 'amount' is not defined`
    and forcing a safety close of a valid position (Full Endurance v3,
    AVAX 514254145).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from croupier.components.oco_manager import OCOManager


def _build_manager():
    manager = OCOManager.__new__(OCOManager)
    manager.logger = MagicMock()
    manager.adapter = MagicMock()
    manager.adapter.price_to_precision = MagicMock(side_effect=lambda s, v: v)
    manager.adapter.register_oco_pair = AsyncMock(return_value=None)
    manager._create_tp_order = AsyncMock(return_value={"order_id": "tp_new", "id": "tp_new"})
    manager._create_sl_order = AsyncMock(return_value={"order_id": "sl_new", "id": "sl_new"})

    manager.tracker = MagicMock()
    manager.tracker.register_bracket_alias = MagicMock()
    manager.tracker.unregister_alias = MagicMock()
    manager.tracker._trigger_state_change = MagicMock()
    return manager


def _make_position(order=None, notional=26.0, entry_price=6.5):
    position = MagicMock()
    position.symbol = "AVAXUSDT"
    position.trade_id = "514254145"
    position.side = "SHORT"
    position.entry_price = entry_price
    position.notional = notional
    position.order = order or {
        "amount": 4.0,
        "tp_price": 6.23,
        "sl_price": 6.65,
    }
    position.tp_order_id = None
    position.exchange_tp_id = None
    position.tp_order = None
    position.sl_order_id = None
    position.exchange_sl_id = None
    position.sl_order = None
    position.tp_level = None
    position.sl_level = None
    position.status = "ACTIVE"
    return position


class TestSmartHealing:
    """restore_bracket must heal without NameError."""

    @pytest.mark.asyncio
    async def test_heals_using_order_amount(self):
        """Full restore path: TP+SL recreated with the position amount."""
        manager = _build_manager()
        position = _make_position()

        result = await manager.restore_bracket(position, missing_tp=True, missing_sl=True)

        assert result is True
        # TP created with the resolved amount (previously NameError here).
        assert manager._create_tp_order.await_count == 1
        tp_args = manager._create_tp_order.await_args.args
        assert tp_args[2] == 4.0
        assert manager._create_sl_order.await_count == 1
        assert position.exchange_tp_id == "tp_new"
        assert position.exchange_sl_id == "sl_new"
        assert position.status == "ACTIVE"

    @pytest.mark.asyncio
    async def test_heals_fallback_amount_from_notional(self):
        """No amount in order dict: derive from notional / entry_price."""
        manager = _build_manager()
        position = _make_position(order={"tp_price": 6.23, "sl_price": 6.65}, notional=26.0, entry_price=6.5)

        result = await manager.restore_bracket(position, missing_tp=True, missing_sl=True)

        assert result is True
        tp_args = manager._create_tp_order.await_args.args
        assert tp_args[2] == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_unresolvable_amount_returns_false_gracefully(self):
        """Zero/negative amount: bail out with warning, no crash."""
        manager = _build_manager()
        position = _make_position(order={"tp_price": 6.23, "sl_price": 6.65}, notional=0.0, entry_price=0.0)
        position.order = {"tp_price": 6.23, "sl_price": 6.65}
        manager.adapter.price_to_precision = MagicMock(side_effect=lambda s, v: v)
        position.entry_price = 0.0
        position.notional = 0.0
        manager.adapter.price_to_precision = MagicMock(side_effect=lambda s, v: v)

        result = await manager.restore_bracket(position, missing_tp=True, missing_sl=True)

        # Sanity check fails earlier (entry_price <= 0) OR amount check:
        # either way NO NameError and no partial bracket creation.
        assert result is False
        manager._create_tp_order.assert_not_awaited()
        manager._create_sl_order.assert_not_awaited()
