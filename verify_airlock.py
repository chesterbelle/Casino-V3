import asyncio
import logging
import os
import sys
import time

# Validate import paths
sys.path.append(os.getcwd())

from exchanges.connectors.binance.binance_native_connector import (  # noqa: E402
    BinanceNativeConnector,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("AirlockVerifier")


async def main():
    connector = BinanceNativeConnector(mode="demo")

    try:
        # 1. Start Connector (Bridge + Sentinel)
        logger.info("🚀 Starting Connector...")
        await connector.connect()

        # 2. Subscribe to high-volume feed
        logger.info("📡 Subscribing to BTCUSDT and ETHUSDT...")
        await connector.subscribe_trades("BTCUSDT")
        await connector.subscribe_trades("ETHUSDT")

        # Warmup
        await asyncio.sleep(5)
        logger.info("✅ Warmup complete. Messages flowing.")

        # 3. THE BLOCK TEST
        duration = 5
        logger.warning(f"🛑 BLOCKING MAIN LOOP for {duration} seconds (Simulating CPU Stall)...")

        # Intentionally block the event loop synchronously
        start_block = time.time()
        time.sleep(duration)  # This killed the old architecture
        end_block = time.time()

        logger.info(f"🔓 Main loop unblocked. Duration: {end_block - start_block:.2f}s")

        # 4. Check Queue backlog
        # If Airlock works, the ingestion_queue should be full of messages from the block period
        backlog_count = 0
        while not connector._ingestion_queue.empty():
            connector._ingestion_queue.get_nowait()
            backlog_count += 1

        logger.info(f"📊 Messages retrieved from Airlock Queue: {backlog_count}")

        if backlog_count > 0:
            logger.info("✅ PASS: Airlock buffered messages during main loop stall.")
        else:
            logger.error("❌ FAIL: No messages in queue after stall. Did the WebSocket die?")

    except Exception as e:
        logger.error(f"Test Failed: {e}", exc_info=True)
    finally:
        # Cleanup
        if connector._ingestion_process:
            connector._ingestion_process.terminate()


if __name__ == "__main__":
    asyncio.run(main())
