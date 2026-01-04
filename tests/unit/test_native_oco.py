import unittest
from unittest.mock import AsyncMock, MagicMock

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


class TestNativeOCO(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create connector with mock API
        self.connector = BinanceNativeConnector(mode="demo")
        self.connector._request = AsyncMock()
        self.connector._normalize_symbol = MagicMock(return_value="BTCUSDT")

        # Mock precision methods
        self.connector.price_to_precision = MagicMock(side_effect=lambda s, p: str(p))
        self.connector.amount_to_precision = MagicMock(side_effect=lambda s, a: str(a))
        self.connector._normalize_algo_order_response = MagicMock(side_effect=lambda r, a: r)

    async def test_create_native_oco_payload(self):
        # Test parameters
        symbol = "BTC/USDT:USDT"
        side = "buy"
        amount = 0.001
        tp_price = 50000.0
        sl_trigger_price = 40000.0
        sl_limit_price = 39900.0

        # Call method
        await self.connector.create_native_oco(
            symbol=symbol,
            side=side,
            amount=amount,
            tp_price=tp_price,
            sl_trigger_price=sl_trigger_price,
            sl_limit_price=sl_limit_price,
            params={"client_order_id": "test_oco_123"},
        )

        # Verify _request call
        self.connector._request.assert_called_once()
        method, path, params = self.connector._request.call_args[0]

        self.assertEqual(method, "POST")
        self.assertEqual(path, "/fapi/v1/algoOrder")

        # Verify OCO params
        self.assertEqual(params["algoType"], "OCO")
        self.assertEqual(params["symbol"], "BTCUSDT")
        self.assertEqual(params["side"], "SELL")  # Flipped from BUY position
        self.assertEqual(params["quantity"], "0.001")
        self.assertEqual(params["profitPrice"], "50000.0")
        self.assertEqual(params["lossPrice"], "40000.0")
        self.assertEqual(params["lossLimitPrice"], "39900.0")
        self.assertEqual(params["type"], "STOP_LOSS_LIMIT")
        self.assertEqual(params["clientAlgoId"], "test_oco_123")
        self.assertEqual(params["reduceOnly"], "true")

    async def test_create_native_oco_market_sl(self):
        # Test OCO with Market SL (no limit price)
        await self.connector.create_native_oco(
            symbol="BTC/USDT:USDT", side="sell", amount=0.005, tp_price=45000.0, sl_trigger_price=55000.0
        )

        _, _, params = self.connector._request.call_args[0]
        self.assertEqual(params["side"], "BUY")  # Flipped from SELL position
        self.assertEqual(params["type"], "STOP_LOSS")
        self.assertNotIn("lossLimitPrice", params)
        self.assertEqual(params["lossPrice"], "55000.0")


if __name__ == "__main__":
    unittest.main()
