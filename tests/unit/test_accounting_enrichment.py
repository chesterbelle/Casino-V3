import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Mock missing dependencies
for module in ["aiolimiter", "eth_account", "eth_abi", "eth_utils", "hexbytes", "websockets"]:
    sys.modules[module] = MagicMock()

from core.observability.historian import TradeHistorian
from croupier.components.order_executor import OrderExecutor


class TestAccountingEnrichment(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.historian = TradeHistorian(db_path=":memory:")
        self.adapter = MagicMock()
        self.executor = OrderExecutor(self.adapter)

    def test_historian_external_closure(self):
        """Test that Historian correctly records an external closure."""
        self.historian.record_external_closure(
            symbol="BTC/USDT:USDT",
            side="LONG",
            qty=0.1,
            entry_price=40000,
            exit_price=41000,
            fee=5.0,
            reason="UNIT_TEST",
        )

        stats = self.historian.get_session_stats()
        # Gross PnL = (41000 - 40000) * 0.1 = 100
        # Net PnL = 100 - 5.0 = 95.0
        self.assertEqual(stats["total_net_pnl"], 95.0)
        self.assertEqual(stats["total_trades"], 1)

    async def test_order_executor_enrichment(self):
        """Test that OrderExecutor enriches fills from trade history."""
        # Mock adapter to return a trade for this order
        self.adapter.fetch_my_trades = AsyncMock(
            return_value=[
                {"order_id": "12345", "price": 41000, "amount": 0.1, "fee": {"cost": 2.5, "currency": "USDT"}}
            ]
        )

        initial_result = {"order_id": "12345", "status": "closed", "symbol": "BTC/USDT:USDT"}

        enriched = await self.executor._enrich_fill_details(initial_result, "BTC/USDT:USDT")

        self.assertEqual(enriched["fee"]["cost"], 2.5)
        self.assertEqual(enriched["average"], 41000)


if __name__ == "__main__":
    unittest.main()
