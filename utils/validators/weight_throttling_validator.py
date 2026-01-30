import asyncio
import logging
import os
import sys
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import exchange as exchange_config
from core.multi_asset_manager import MultiAssetManager
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("WeightValidator")


async def run_validator():
    logger.info("🚀 Starting Weight Throttling Validator...")

    connector = BinanceNativeConnector(
        api_key=exchange_config.BINANCE_API_KEY, secret=exchange_config.BINANCE_API_SECRET, mode="demo"
    )
    await connector.connect()

    manager = MultiAssetManager(connector)

    # Phase 102: Industrial Resilience - Set a lower limit for testing
    # Binance Futures default is 1200. We'll set it to 100 for fast trigger.
    connector._rate_limiter._weight_limit = 100
    logger.info(f"⚙️ Test Weight Limit: {connector._rate_limiter._weight_limit}")

    # 1. Baseline: Run a few iterations and measure time
    logger.info("📊 Measuring baseline (Low Load)...")
    start = time.time()
    for _ in range(5):
        await manager._check_rate_limit_throttle()
    baseline_duration = time.time() - start
    logger.info(f"✅ Baseline duration: {baseline_duration:.4f}s")

    # 2. Inflate Weight: Fire bulk tickers until load > 80%
    logger.info("🔥 Inflating API Weight (Bulk Tickers)...")
    while connector.get_load_factor() < 0.85:
        await connector.fetch_tickers()
        load = connector.get_load_factor()
        if int(load * 100) % 10 == 0:
            logger.info(f"📈 Current Load: {load:.2%}")
        await asyncio.sleep(0.1)  # Small delay to not hit hard per-second limit

    logger.info(f"🚩 TARGET REACHED: Load is {connector.get_load_factor():.2%}")

    # 3. Test Throttling: Measure duration again
    logger.info("🧪 Testing Throttling (High Load)...")
    start = time.time()
    # It should trigger at least 1s delay per call if > 80%
    await manager._check_rate_limit_throttle()
    throttled_duration = time.time() - start

    logger.info(f"✅ Throttled duration: {throttled_duration:.4f}s")

    if throttled_duration > 0.9:
        logger.info("🎊 SUCCESS: Adaptive Throttling is ACTIVE and working!")
    else:
        logger.error("❌ FAILURE: No throttling detected despite high load.")

    await connector.close()


if __name__ == "__main__":
    asyncio.run(run_validator())
