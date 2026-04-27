import logging
import unittest
from unittest.mock import MagicMock, patch

from core.portfolio.position_tracker import OpenPosition
from croupier.components.exit_engine import ExitEngine


class TestATRExits(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.croupier = MagicMock()
        self.logger = logging.getLogger("TestATR")
        self.exit_manager = ExitEngine(self.croupier)

        # Mock config
        self.patcher = patch("croupier.components.exit_engine.config")
        self.mock_config = self.patcher.start()
        self.mock_config.BREAKEVEN_ENABLED = True
        self.mock_config.TRAILING_STOP_ENABLED = True
        self.mock_config.BREAKEVEN_ACTIVATION_PCT = 0.0015  # 0.15% default
        self.mock_config.TRAILING_STOP_ACTIVATION_PCT = 0.0020  # 0.20% default
        self.mock_config.TRAILING_STOP_DISTANCE_PCT = 0.0008  # 0.08% default
        self.mock_config.EXIT_ATR_MULT_TS = 1.5
        self.mock_config.EXIT_ATR_MULT_BE = 2.0

    def tearDown(self):
        self.patcher.stop()

    async def test_atr_breakeven_long(self):
        """Verify Breakeven activation threshold scales with ATR (LONG)."""
        pos = OpenPosition(
            trade_id="T1",
            symbol="BTC/USDT:USDT",
            side="LONG",
            entry_price=100.0,
            entry_timestamp="0",
            margin_used=0,
            notional=100.0,
            leverage=1,
            tp_level=110.0,
            sl_level=90.0,
            liquidation_level=0,
            order={},
            status="ACTIVE",
            entry_atr=1.0,  # 1% volatility
        )

        # Test 1: Price moved 1.5x ATR (101.5) -> Should NOT activate (BE mult is 2.0x)
        # But it WILL initialize shadow_sl_level to 90.0
        await self.exit_manager._check_shadow_breakeven(pos, 101.5)
        self.assertEqual(pos.shadow_sl_level, 90.0)

        # Test 2: Price moved 2.1x ATR (102.1) -> SHOULD activate
        await self.exit_manager._check_shadow_breakeven(pos, 102.1)
        self.assertEqual(pos.shadow_sl_level, 100.1)  # entry * 1.001

    async def test_atr_trailing_stop_short(self):
        """Verify Trailing Stop distance scales with ATR (SHORT)."""
        pos = OpenPosition(
            trade_id="T2",
            symbol="BTC/USDT:USDT",
            side="SHORT",
            entry_price=100.0,
            entry_timestamp="0",
            margin_used=0,
            notional=100.0,
            leverage=1,
            tp_level=90.0,
            sl_level=110.0,
            liquidation_level=0,
            order={},
            status="ACTIVE",
            entry_atr=2.0,  # 2% volatility
        )

        # Profit must be > 0.20% (Trailing Activation)
        # Price 99.0 (1% profit)

        # Trailing distance = 1.5x * 2.0 ATR = 3.0
        # New SL should be 99.0 + 3.0 = 102.0
        await self.exit_manager._check_shadow_trailing_stop(pos, 99.0)

        self.assertEqual(pos.shadow_sl_level, 102.0)

        # Price drops further to 98.0
        # New SL should be 98.0 + 3.0 = 101.0
        await self.exit_manager._check_shadow_trailing_stop(pos, 98.0)
        self.assertEqual(pos.shadow_sl_level, 101.0)


if __name__ == "__main__":
    unittest.main()
