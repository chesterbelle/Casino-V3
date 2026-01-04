import unittest
from unittest.mock import AsyncMock, MagicMock

from core.portfolio.position_tracker import OpenPosition, PositionTracker
from croupier.components.oco_manager import OCOManager
from exchanges.adapters.exchange_adapter import ExchangeAdapter


class TestOCOManagerNative(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock dependencies
        self.adapter = MagicMock(spec=ExchangeAdapter)
        self.executor = MagicMock()
        self.tracker = PositionTracker(adapter=self.adapter)

        # Initialize OCOManager with positional args
        self.oco_manager = OCOManager(self.executor, self.tracker, self.adapter)

        # Mock adapter methods
        self.adapter.supports_native_oco = True
        self.adapter.price_to_precision = MagicMock(side_effect=lambda s, p: str(p))
        self.adapter.get_current_price = AsyncMock(return_value=100.0)
        self.adapter.register_oco_pair = AsyncMock()

    async def test_create_bracketed_order_native(self):
        # Mock main order fill
        main_order = {
            "id": "main_123",
            "order_id": "main_123",
            "amount": 10.0,
            "price": 100.0,
            "status": "closed",
            "timestamp": 12345678,
            "symbol": "BTC/USDT:USDT",
        }

        # Mock inner methods
        self.oco_manager._execute_main_order = AsyncMock(return_value=main_order)
        self.oco_manager._wait_for_fill = AsyncMock(return_value=100.0)

        # Mock Native OCO result
        self.adapter.create_native_oco_bracket = AsyncMock(return_value={"id": "native_oco_456", "status": "open"})

        # Strategy order
        order = {
            "symbol": "BTC/USDT:USDT",
            "side": "LONG",
            "amount": 10.0,
            "take_profit": 0.05,
            "stop_loss": 0.02,
            "leverage": 10,
            "margin_used": 10.0,
            "notional": 100.0,
        }

        # Run execution
        result = await self.oco_manager.create_bracketed_order(order)

        # Verify Native OCO was called
        self.adapter.create_native_oco_bracket.assert_called_once()

        # Verify position state
        position = self.tracker.get_position("main_123")
        self.assertIsNotNone(position)
        self.assertEqual(position.status, "ACTIVE")
        self.assertEqual(position.tp_order_id, "native_oco_456")
        self.assertEqual(position.sl_order_id, "native_oco_456")

    async def test_modify_bracket_native(self):
        # Setup active position with native OCO
        position = OpenPosition(
            trade_id="pos_789",
            symbol="BTC/USDT",
            side="LONG",
            entry_price=100.0,
            entry_timestamp="2026-01-01T00:00:00",
            margin_used=10.0,
            notional=100.0,
            leverage=10.0,
            tp_level=105.0,
            sl_level=95.0,
            liquidation_level=80.0,
            order={"amount": 1.0},
            exchange_tp_id="native_oco_old",
            exchange_sl_id="native_oco_old",
            status="ACTIVE",
        )
        self.tracker.open_positions.append(position)

        # Mock modification
        self.oco_manager.cancel_order = AsyncMock()
        self.adapter.create_native_oco_bracket = AsyncMock(return_value={"id": "native_oco_new", "status": "open"})

        # Call modify
        await self.oco_manager.modify_bracket(trade_id="pos_789", symbol="BTC/USDT", new_sl_price=98.0)

        # Verify: 1. Cancelled old OCO, 2. Created new OCO, 3. Updated IDs
        self.oco_manager.cancel_order.assert_called_with("native_oco_old", "BTC/USDT")
        self.adapter.create_native_oco_bracket.assert_called_once()
        self.assertEqual(position.exchange_sl_id, "native_oco_new")
        self.assertEqual(position.exchange_tp_id, "native_oco_new")


if __name__ == "__main__":
    unittest.main()
