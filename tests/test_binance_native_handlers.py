"""
Tests for BinanceNativeConnector WebSocket handlers and fetch_my_trades.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


class TestBinanceNativeConnectorWebSocket:
    """Tests for WebSocket event handlers."""

    @pytest.fixture
    def connector(self):
        """Create connector instance for testing."""
        connector = BinanceNativeConnector(mode="demo", enable_websocket=False)
        connector._connected = True
        return connector

    def test_handle_order_update_basic(self, connector):
        """Test basic order update handling."""
        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "E": 1699000000000,
            "o": {
                "i": "12345",
                "s": "BTCUSDT",
                "X": "FILLED",
                "S": "BUY",
                "o": "MARKET",
                "p": "50000.0",
                "ap": "50050.0",
                "q": "0.1",
                "z": "0.1",
            },
        }

        connector._handle_order_update(msg)

        assert hasattr(connector, "_orders_cache")
        assert "12345" in connector._orders_cache
        order = connector._orders_cache["12345"]
        assert order["id"] == "12345"
        assert order["symbol"] == "BTCUSDT"
        assert order["status"] == "filled"
        assert order["side"] == "buy"
        assert order["price"] == 50050.0
        assert order["filled"] == 0.1

    def test_handle_order_update_no_data(self, connector):
        """Test order update with missing data."""
        msg = {"e": "ORDER_TRADE_UPDATE", "E": 1699000000000}

        # Should not raise exception
        connector._handle_order_update(msg)

        # Should not create cache entry
        if hasattr(connector, "_orders_cache"):
            assert len(connector._orders_cache) == 0

    def test_handle_account_update_balance(self, connector):
        """Test account update with balance changes."""
        msg = {
            "e": "ACCOUNT_UPDATE",
            "E": 1699000000000,
            "a": {
                "B": [
                    {"a": "USDT", "wb": "10000.0", "cw": "8000.0"},
                    {"a": "BTC", "wb": "0.5", "cw": "0.3"},
                ]
            },
        }

        connector._handle_account_update(msg)

        assert hasattr(connector, "_balance_cache")
        assert connector._balance_cache["total"]["USDT"] == 10000.0
        assert connector._balance_cache["free"]["USDT"] == 8000.0
        assert connector._balance_cache["used"]["USDT"] == 2000.0
        assert connector._balance_cache["total"]["BTC"] == 0.5

    def test_handle_account_update_positions(self, connector):
        """Test account update with position changes."""
        msg = {
            "e": "ACCOUNT_UPDATE",
            "E": 1699000000000,
            "a": {
                "P": [
                    {
                        "s": "BTCUSDT",
                        "pa": "0.1",
                        "ep": "50000.0",
                        "mp": "51000.0",
                        "up": "100.0",
                    },
                    {
                        "s": "ETHUSDT",
                        "pa": "-0.5",
                        "ep": "3000.0",
                        "mp": "2950.0",
                        "up": "25.0",
                    },
                ]
            },
        }

        connector._handle_account_update(msg)

        assert hasattr(connector, "_positions_cache")
        assert len(connector._positions_cache) == 2

        btc_pos = next(p for p in connector._positions_cache if p["symbol"] == "BTCUSDT")
        assert btc_pos["side"] == "LONG"
        assert btc_pos["size"] == 0.1
        assert btc_pos["entry_price"] == 50000.0

        eth_pos = next(p for p in connector._positions_cache if p["symbol"] == "ETHUSDT")
        assert eth_pos["side"] == "SHORT"
        assert eth_pos["size"] == 0.5

    def test_handle_account_update_no_data(self, connector):
        """Test account update with missing data."""
        msg = {"e": "ACCOUNT_UPDATE", "E": 1699000000000}

        # Should not raise exception
        connector._handle_account_update(msg)


class TestBinanceNativeConnectorTrades:
    """Tests for fetch_my_trades method."""

    @pytest.fixture
    def connector(self):
        """Create connector instance for testing."""
        connector = BinanceNativeConnector(mode="demo", enable_websocket=False)
        connector._connected = True
        # Mock the client
        connector.client = MagicMock()
        return connector

    @pytest.mark.asyncio
    async def test_fetch_my_trades_basic(self, connector):
        """Test basic fetch_my_trades."""
        mock_trades = [
            {
                "id": "123",
                "orderId": "456",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "price": "50000.0",
                "qty": "0.1",
                "quoteQty": "5000.0",
                "commission": "2.5",
                "commissionAsset": "USDT",
                "time": 1699000000000,
            }
        ]

        connector.client.get_account_trades.return_value = mock_trades

        trades = await connector.fetch_my_trades(symbol="BTC/USDT:USDT")

        assert len(trades) == 1
        trade = trades[0]
        assert trade["id"] == "123"
        assert trade["order"] == "456"
        assert trade["symbol"] == "BTCUSDT"
        assert trade["side"] == "buy"
        assert trade["price"] == 50000.0
        assert trade["amount"] == 0.1
        assert trade["cost"] == 5000.0
        assert trade["fee"]["cost"] == 2.5
        assert trade["fee"]["currency"] == "USDT"

    @pytest.mark.asyncio
    async def test_fetch_my_trades_with_filters(self, connector):
        """Test fetch_my_trades with filters."""
        connector.client.get_account_trades.return_value = []

        await connector.fetch_my_trades(symbol="BTC/USDT:USDT", since=1699000000000, limit=50)

        # Verify correct parameters were passed
        call_args = connector.client.get_account_trades.call_args[1]
        assert call_args["symbol"] == "BTCUSDT"
        assert call_args["startTime"] == 1699000000000
        assert call_args["limit"] == 50
        assert "timestamp" in call_args
        assert "recvWindow" in call_args

    @pytest.mark.asyncio
    async def test_fetch_my_trades_limit_cap(self, connector):
        """Test that limit is capped at 1000."""
        connector.client.get_account_trades.return_value = []

        await connector.fetch_my_trades(limit=2000)

        call_args = connector.client.get_account_trades.call_args[1]
        assert call_args["limit"] == 1000  # Should be capped


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
