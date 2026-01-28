import asyncio
import logging
import os

# from config import exchange as exchange_config
from core.error_handling.error_handler import get_error_handler
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("DebugReduceOnly")


async def test_reduce_only_conflict():
    logger.info("🧪 Starting ReduceOnly Conflict Test...")

    # 1. Initialize Connector
    connector = BinanceNativeConnector(
        api_key=os.getenv("BINANCE_TESTNET_API_KEY"), secret=os.getenv("BINANCE_TESTNET_SECRET"), mode="demo"
    )

    error_handler = get_error_handler()
    connector.error_handler = error_handler

    symbol = "BTCUSDT"
    qty = 0.005  # Min notional > 100 on BTC is usually 0.002, trying slightly larger

    try:
        await connector.connect()
        logger.info("✅ Connected to Binance Testnet")

        # 2. Open a Position (LONG)
        logger.info(f"🚀 Opening Position: BUY {qty} {symbol}...")
        order_open = await connector.create_order(symbol=symbol, side="BUY", order_type="MARKET", amount=qty)
        logger.info(f"✅ Open Order Success: {order_open.get('orderId')}")
        await asyncio.sleep(2)  # Wait for fill

        current_price = float(order_open.get("avgPrice", 0) or 50000)  # Fallback if instant
        logger.info(f"💰 Entry Price: {current_price}")

        tp_price = round(current_price * 1.05, 1)
        sl_price = round(current_price * 0.95, 1)

        # 3. Place TP (TAKE_PROFIT_MARKET ReduceOnly) - The Fix
        logger.info(f"🛑 Placing TP (MK-TP ReduceOnly): SELL {qty} @ {tp_price}...")
        try:
            tp_order = await connector.create_order(
                symbol=symbol,
                side="SELL",
                order_type="TAKE_PROFIT_MARKET",
                amount=qty,
                stop_price=tp_price,
                params={"reduceOnly": True, "timeInForce": "GTC"},
            )
            logger.info(f"✅ TP Order Placed: {tp_order.get('orderId')}")
        except Exception as e:
            logger.error(f"❌ TP Failed: {e}")

        # 4. Place SL (Stop Market ReduceOnly)
        logger.info(f"🛑 Placing SL (Stop Market ReduceOnly): SELL {qty} @ Trigger {sl_price}...")
        try:
            sl_order = await connector.create_order(
                symbol=symbol,
                side="SELL",
                order_type="STOP_MARKET",
                amount=qty,
                stop_price=sl_price,
                params={"reduceOnly": True},  # Phase 98 should route this to Algo API
            )
            logger.info(f"✅ SL Order Placed: {sl_order.get('orderId')}")
        except Exception as e:
            logger.error(f"❌ SL Failed: {e}")

    except Exception as e:
        logger.error(f"💥 Critical Error: {e}")
    finally:
        # Cleanup
        logger.info("🧹 Cleaning up...")
        await connector.create_order(
            symbol=symbol, side="SELL", order_type="MARKET", amount=qty, params={"reduceOnly": True}
        )
        await connector.disconnect()


if __name__ == "__main__":
    asyncio.run(test_reduce_only_conflict())
