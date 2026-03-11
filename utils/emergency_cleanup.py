import asyncio
import logging
import os
import sys

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


async def cleanup():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Cleanup")

    connector = BinanceNativeConnector(
        api_key=os.getenv("BINANCE_API_KEY_DEMO"), secret=os.getenv("BINANCE_API_SECRET_DEMO"), mode="demo"
    )

    try:
        await connector.connect()
        logger.info("📡 Connected to Binance Testnet")

        # 1. Fetch all symbols with open positions or orders
        active_symbols = await connector.fetch_active_symbols()
        logger.info(f"🔍 Found {len(active_symbols)} symbols with activity: {active_symbols}")

        for symbol in active_symbols:
            logger.info(f"🧹 Cleaning up {symbol}...")
            # Cancel all orders
            try:
                await connector.cancel_all_orders(symbol)
                logger.info(f"✅ Cancelled all orders for {symbol}")
            except Exception as e:
                logger.error(f"❌ Failed to cancel orders for {symbol}: {e}")

            # Close positions (Market)
            try:
                positions = await connector.fetch_positions(symbol)
                for pos in positions:
                    size = float(pos.get("info", {}).get("positionAmt", 0))
                    if abs(size) > 0:
                        side = "sell" if size > 0 else "buy"
                        logger.info(f"📉 Closing position for {symbol}: {side} {abs(size)}")
                        await connector.create_market_order(symbol, side, abs(size), params={"reduceOnly": True})
                        logger.info(f"✅ Closed position for {symbol}")
            except Exception as e:
                logger.error(f"❌ Failed to close position for {symbol}: {e}")

        logger.info("✨ Cleanup complete!")
    finally:
        await connector.close()


if __name__ == "__main__":
    asyncio.run(cleanup())
