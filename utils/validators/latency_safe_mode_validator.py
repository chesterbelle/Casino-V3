import asyncio
import logging
import time

from core.exceptions import ExchangeError
from croupier.components.order_executor import OrderExecutor
from exchanges.adapters.exchange_adapter import ExchangeAdapter
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("SafeModeValidator")


async def validate_safe_mode():
    logger.info("🚀 Starting Latency Safe Mode Validation...")

    # 1. Setup
    connector = BinanceNativeConnector(mode="demo", enable_websocket=False)
    adapter = ExchangeAdapter(connector=connector, symbol="LTCUSDT")
    executor = OrderExecutor(exchange_adapter=adapter)

    # 2. Induce Congestion
    logger.info("🧪 Test 1: Inducing Congestion (>800ms)...")
    monitor = connector._latency_monitor
    for _ in range(10):
        monitor.record_latency(950.0)  # Solidly above threshold

    logger.info(f"📊 Stats: {monitor.get_stats()}")
    assert monitor.is_congested, "Monitor should be congested!"
    assert adapter.is_congested, "Adapter should report congestion!"

    # 3. Attempt Entry (Should Fail)
    logger.info("📤 Attempting Market Entry during congestion...")
    order = {"symbol": "LTCUSDT", "side": "buy", "amount": 0.1}
    try:
        await executor.execute_market_order(order)
        logger.error("❌ FAILURE: Entry allowed during congestion!")
    except ExchangeError as e:
        logger.info(f"✅ SUCCESS: Entry rejected as expected: {e}")
    except Exception as e:
        logger.error(f"❌ FAILURE: Unexpected error type: {type(e).__name__}: {e}")

    # 4. Attempt Exit (Should Pass - but will fail on actual API, so we check if it REACHES the API)
    logger.info("📤 Attempting reduceOnly (Exit) during congestion...")
    exit_order = {"symbol": "LTCUSDT", "side": "sell", "amount": 0.1, "params": {"reduceOnly": True}}

    try:
        # We expect a Binance Error (or auth error if no keys), NOT a Safe Mode rejection
        await executor.execute_market_order(exit_order)
    except Exception as e:
        if "Safe Mode Active" in str(e):
            logger.error(f"❌ FAILURE: Exit order was blocked by Safe Mode! Error: {e}")
        else:
            logger.info(
                f"✅ SUCCESS: Exit order bypassed Safe Mode (reached API/ErrorHandler): {type(e).__name__}: {e}"
            )

    # 5. Clear Congestion
    logger.info("🧪 Test 2: Clearing Congestion (<800ms)...")
    for _ in range(60):  # Window is 50, need to flush it
        monitor.record_latency(150.0)

    logger.info(f"📊 Stats: {monitor.get_stats()}")
    assert not monitor.is_congested, "Congestion should be cleared!"

    # 6. Attempt Entry (Should Pass to API)
    logger.info("📤 Attempting Market Entry after clearing...")
    try:
        await executor.execute_market_order(order)
    except ExchangeError as e:
        if "Safe Mode Active" in str(e):
            logger.error("❌ FAILURE: Entry still blocked after clearing!")
        else:
            logger.info(f"✅ SUCCESS: Entry allowed again (reached API/ErrorHandler): {e}")

    logger.info("🏁 Validation Complete.")


if __name__ == "__main__":
    asyncio.run(validate_safe_mode())
