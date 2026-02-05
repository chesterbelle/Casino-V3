import time
import unittest


class TestReconciliationLogicSimplified(unittest.TestCase):
    def test_extraction_logic(self):
        """
        Verify that the new extraction logic correctly handles the normalized keys.
        """
        # Simulated open_orders as returned by BinanceNativeConnector (normalized)
        open_orders = [
            {
                "id": "10001",
                "order_id": "10001",
                "client_order_id": "TP_CLIENT_123",
                "symbol": "BTCUSDT",
                "status": "open",
            },
            {
                "id": "10002",
                "order_id": "10002",
                "client_order_id": "SL_CLIENT_123",
                "symbol": "BTCUSDT",
                "status": "open",
            },
        ]

        # New extraction logic from reconciliation_service.py
        open_order_ids = {str(o.get("order_id") or o.get("id")) for o in open_orders}
        open_client_ids = {str(o.get("client_order_id")) for o in open_orders if o.get("client_order_id")}

        # Assertions
        self.assertIn("10001", open_order_ids)
        self.assertIn("10002", open_order_ids)
        self.assertIn("TP_CLIENT_123", open_client_ids)
        self.assertIn("SL_CLIENT_123", open_client_ids)

        # Verification of the bug: old keys would fail
        open_client_ids_old = {str(o.get("clientOrderId")) for o in open_orders}
        # o.get("clientOrderId") returns None for both, so set becomes {'None'}
        self.assertSetEqual(open_client_ids_old, {"None"})

    def test_young_position_detect(self):
        # entry_timestamp is in milliseconds
        now_ms = time.time() * 1000
        entry_time_ms = now_ms - 10000  # 10s ago

        is_young = (time.time() * 1000 - entry_time_ms) < 60000
        self.assertTrue(is_young)


if __name__ == "__main__":
    unittest.main()
