"""
Test para WebSocket de Binance Native
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


@pytest.mark.asyncio
async def test_websocket_structure():
    """Test básico de estructura WebSocket (Mocked)."""
    print("=" * 80)
    print("🧪 TEST: WebSocket Structure (Binance Native)")
    print("=" * 80)

    # 1. Crear conector
    connector = BinanceNativeConnector(mode="demo", enable_websocket=True)

    # Mock SDK client
    connector.client = MagicMock()
    connector.client.time.return_value = {"serverTime": 1699000000000}
    connector.client.exchange_info.return_value = {"symbols": []}
    connector.client.new_listen_key.return_value = {"listenKey": "test_key"}

    # Mock WebSocket client class
    with unittest.mock.patch(
        "exchanges.connectors.binance.binance_native_connector.UMFuturesWebsocketClient"
    ) as MockWS:
        mock_ws_instance = MockWS.return_value

        # 2. Conectar (Mocked)
        await connector.connect()

        assert connector.is_connected
        assert connector.ws_client is not None
        assert connector.ws_client == mock_ws_instance

        # Verify subscription
        mock_ws_instance.user_data.assert_called()
        print("✅ WebSocket client initialized and subscribed to user data")

    # 3. Simulate Message
    msg = {"e": "ORDER_TRADE_UPDATE", "o": {"i": "123", "s": "BTCUSDT", "X": "FILLED"}}
    connector._on_ws_message(None, msg)
    # (Verification of internal state update would go here)

    await connector.close()
    print("✅ Connection closed")


if __name__ == "__main__":
    asyncio.run(test_websocket_structure())
