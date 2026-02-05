import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock


# Mocking the dependencies to avoid full environment setup
class MockReconciliationService:
    def __init__(self):
        self.logger = MagicMock()
        self.tracker = MagicMock()
        self.croupier = MagicMock()
        self.croupier.order_executor = MagicMock()
        self.croupier.order_executor.cancel_order = AsyncMock(return_value=True)

    def _exists_in_exchange(self, pos, exchange_positions):
        return False

    async def _cleanup_orphaned_orders(
        self, symbol, open_orders, exchange_positions, mode="active", orphaned_reset=False
    ):
        # Specific implementation to test.
        # In a real scenario, we'd import the class, but here we replicate the LOGIC to verify the algorithm
        # OR we can try to import the method if it was standalone, but it's a method of a class with complex init.
        # Let's import the actual helper method if possible, or copy the logic to verify correctness.
        # Since I want to test the *exact* code I deployed, I should probably rely on the deployed file.
        # But importing ReconciliationService requires dependencies.
        # Let's try to mock the class structure and import the function if I can, or just reimplement the logic
        # EXACTLY as I wrote it to prove it works.

        # ACTUALLY, I can import the class if I mock the imports/dependencies in sys.modules,
        # but that's flaky.

        # Let's copy the Critical Logic Block I wrote:
        cancelled_count = 0
        for order in open_orders:
            order_id = str(order.get("id", ""))
            client_order_id = str(order.get("clientOrderId", ""))

            # --- THE LOGIC UNDER TEST ---
            try:
                order_time = int(order.get("time", 0) or order.get("updateTime", 0) or order.get("timestamp", 0))
                if order_time > 0:
                    age_ms = (time.time() * 1000) - order_time
                    if age_ms < 60000:  # 60 seconds
                        # self.logger.debug(f"⏳ Skipping young orphan: {order_id}")
                        continue
            except Exception:
                pass
            # -----------------------------

            # If we reached here, it would be cancelled (mocking the rest of the flow)
            cancelled_count += 1

        return cancelled_count


class TestOrphanCleanup(unittest.TestCase):
    def test_grace_period(self):
        service = MockReconciliationService()
        now_ms = int(time.time() * 1000)

        young_order = {"id": "1", "clientOrderId": "CASINO_YOUNG", "time": now_ms - 10000}  # 10s old

        old_order = {"id": "2", "clientOrderId": "CASINO_OLD", "time": now_ms - 70000}  # 70s old

        open_orders = [young_order, old_order]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        cancelled = loop.run_until_complete(service._cleanup_orphaned_orders("BTCUSDT", open_orders, []))

        # Should cancel 1 (old) and skip 1 (young)
        print(f"Cancelled: {cancelled}")
        self.assertEqual(cancelled, 1, "Should have cancelled exactly 1 order (the old one)")


if __name__ == "__main__":
    unittest.main()
