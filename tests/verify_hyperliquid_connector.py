import asyncio
import logging
import os
import sys
from unittest.mock import AsyncMock, patch

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges.connectors.hyperliquid.hyperliquid_connector import HyperliquidConnector
from exchanges.connectors.hyperliquid.hyperliquid_constants import (
    denormalize_symbol,
    normalize_symbol,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyHyperliquid")


async def test_normalization():
    logger.info("Testing symbol normalization...")

    # Test 1: Bot to Hyperliquid
    bot_symbol = "BTC/USD:USD"
    hl_symbol = normalize_symbol(bot_symbol)
    assert hl_symbol == "BTC/USDC:USDC", f"Expected BTC/USDC:USDC, got {hl_symbol}"
    logger.info(f"✅ {bot_symbol} -> {hl_symbol}")

    # Test 2: Hyperliquid to Bot
    hl_symbol_in = "BTC/USDC:USDC"
    bot_symbol_out = denormalize_symbol(hl_symbol_in)
    assert bot_symbol_out == "BTC/USD:USD", f"Expected BTC/USD:USD, got {bot_symbol_out}"
    logger.info(f"✅ {hl_symbol_in} -> {bot_symbol_out}")

    logger.info("✅ Normalization tests passed")


async def test_connector_structure():
    logger.info("Testing connector structure...")

    connector = HyperliquidConnector(api_key="dummy", secret="dummy", mode="testing", enable_websocket=False)

    # Check inheritance
    from exchanges.connectors.connector_base import BaseConnector

    assert isinstance(connector, BaseConnector)

    # Check methods exist
    assert hasattr(connector, "connect")
    assert hasattr(connector, "create_order")
    assert hasattr(connector, "fetch_balance")
    assert hasattr(connector, "fetch_positions")
    assert hasattr(connector, "fetch_ohlcv")

    logger.info("✅ Connector structure tests passed")


async def test_connect_mock():
    logger.info("Testing connect() with mocks...")

    with patch("ccxt.async_support.hyperliquid") as MockCCXT:
        # Setup mock
        mock_exchange = AsyncMock()
        mock_exchange.markets = {"BTC/USDC:USDC": {"id": "BTC"}}
        mock_exchange.load_markets.return_value = mock_exchange.markets
        mock_exchange.fetch_balance.return_value = {"total": {"USDC": 1000}}
        MockCCXT.return_value = mock_exchange

        connector = HyperliquidConnector(api_key="dummy", secret="dummy", mode="testing", enable_websocket=False)

        await connector.connect()

        assert connector.is_connected
        assert connector.ready

        # Verify calls
        mock_exchange.load_markets.assert_called_once()
        mock_exchange.fetch_balance.assert_called_once()

        logger.info("✅ Connect mock tests passed")


async def test_trade_normalization():
    logger.info("Testing trade normalization...")

    connector = HyperliquidConnector(api_key="dummy", secret="dummy", mode="testing", enable_websocket=False)

    # Test 1: Normal trade
    raw_trade = {"id": "1", "info": {"closedPnl": "0.0"}, "reduceOnly": False}
    norm = connector.normalize_trade(raw_trade)
    assert not norm["is_close"]
    assert norm["realized_pnl"] == 0.0

    # Test 2: Close trade (reduceOnly)
    raw_trade_close = {"id": "2", "info": {"closedPnl": "10.5"}, "reduceOnly": True}
    norm_close = connector.normalize_trade(raw_trade_close)
    assert norm_close["is_close"]
    assert norm_close["realized_pnl"] == 10.5

    # Test 3: Close trade (via PnL)
    raw_trade_pnl = {"id": "3", "info": {"closedPnl": "-5.0"}, "reduceOnly": False}
    norm_pnl = connector.normalize_trade(raw_trade_pnl)
    assert norm_pnl["is_close"]
    assert norm_pnl["realized_pnl"] == -5.0

    logger.info("✅ Trade normalization tests passed")


async def main():
    try:
        await test_normalization()
        await test_connector_structure()
        await test_connect_mock()
        await test_trade_normalization()
        logger.info("🎉 All tests passed!")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
