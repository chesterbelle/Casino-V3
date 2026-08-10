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

    # Mock _request for initialization
    async def mock_request(method, endpoint, *args, **kwargs):
        if endpoint == "/fapi/v1/time":
            return {"serverTime": int(time.time() * 1000)}
        elif endpoint == "/fapi/v1/exchangeInfo":
            return {"symbols": []}
        elif endpoint == "/fapi/v1/positionSide/dual":
            return {"dualSidePosition": False}
        elif endpoint == "/fapi/v1/listenKey":
            return {"listenKey": "test_key"}
        return {}

    connector._request = MagicMock(side_effect=mock_request)

    # Mock WebSocket connect
    import time

    with unittest.mock.patch("websockets.connect", new_callable=unittest.mock.AsyncMock) as MockWS:
        mock_ws_instance = MockWS.return_value

        # 2. Conectar (Mocked)
        await connector.connect()

        assert connector.is_connected
        print("✅ WebSocket client initialized and tasks started")

    await connector.close()
    print("✅ Connection closed")


if __name__ == "__main__":
    asyncio.run(test_websocket_structure())
