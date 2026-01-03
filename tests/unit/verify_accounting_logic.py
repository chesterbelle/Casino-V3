import sys
from unittest.mock import AsyncMock, MagicMock

# Mock EVERYTHING that is not needed
for module in [
    "aiolimiter",
    "eth_account",
    "eth_abi",
    "eth_utils",
    "hexbytes",
    "websockets",
    "hyperliquid",
    "hyperliquid.exchange",
    "hyperliquid.info",
    "hyperliquid.utils",
    "ccxt",
    "ccxt.pro",
]:
    sys.modules[module] = MagicMock()

import os
import unittest

# Add the project root to sys.path
sys.path.append(os.getcwd())

# Import the components we want to test
from core.observability.historian import TradeHistorian
from croupier.components.order_executor import OrderExecutor


class TestAccountingLogic(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Use a fresh in-memory DB for each test
        self.historian = TradeHistorian(db_path=":memory:")
        self.adapter = AsyncMock()
        self.executor = OrderExecutor(self.adapter)

    def test_record_external_closure(self):
        """Verify that Historian correctly records brute-force or recon closures."""
        self.historian.record_external_closure(
            symbol="ETH/USDT:USDT",
            side="SHORT",
            qty=1.0,
            entry_price=2500,
            exit_price=2400,
            fee=2.0,
            reason="FORCE_TEST",
            session_id="session_123",
        )

        stats = self.historian.get_session_stats(session_id="session_123")
        # Gross = (Entry 2500 - Exit 2400) * 1.0 = 100 (Short win)
        # Net = 100 - 2.0 = 98.0
        self.assertEqual(stats["total_net_pnl"], 98.0)
        self.assertEqual(stats["count"], 1)

    async def test_order_enrichment(self):
        """Verify that OrderExecutor can recover fees from trade history."""
        order_id = "test_order_789"

        # Mock adapter to return trades when asked
        self.adapter.fetch_my_trades = AsyncMock(
            return_value=[
                {"order_id": order_id, "price": 2450.0, "amount": 1.0, "fee": {"cost": 1.5, "currency": "USDT"}}
            ]
        )

        initial_res = {"order_id": order_id, "status": "closed", "symbol": "ETH/USDT:USDT"}

        enriched = await self.executor._enrich_fill_details(initial_res, "ETH/USDT:USDT")

        self.assertEqual(enriched["fee"]["cost"], 1.5)
        self.assertEqual(enriched["average"], 2450.0)


if __name__ == "__main__":
    unittest.main()
