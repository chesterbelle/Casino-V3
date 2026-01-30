import asyncio
import logging
import os
import sys
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import exchange as exchange_config
from croupier.components.order_executor import OrderExecutor
from exchanges.adapters import ExchangeAdapter
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("FragValidator")


async def run_validator():
    logger.info("🚀 Starting Fragmentation Validator...")

    symbol = "KAVAUSDT"
    connector = BinanceNativeConnector(
        api_key=exchange_config.BINANCE_API_KEY, secret=exchange_config.BINANCE_API_SECRET, mode="demo"
    )
    await connector.connect()

    adapter = ExchangeAdapter(connector, symbol)
    executor = OrderExecutor(adapter)

    # Force a lower fragmentation threshold for the test
    executor.fragmentation_threshold_pct = -1.0  # Always trigger
    logger.info(f"⚙️ Test Frag Threshold: {executor.fragmentation_threshold_pct:.4%}")

    # 1. Execute a "large" order
    # I'll use a very large amount to ensure chunks are > $5 notional
    amount = 500.0
    logger.info(f"🧪 Testing Fragmented Execution: {amount} {symbol}")

    order = {"symbol": symbol, "side": "buy", "amount": amount, "params": {"test_fragmentation": True}}

    start_time = time.time()
    await executor.execute_market_order(order)
    duration = time.time() - start_time

    logger.info(f"✅ Execution Complete. Duration: {duration:.2f}s")

    # 2. Verify results
    # Fragmented execution takes 3 chunks with 0.5s delay -> at least 1s total
    if duration >= 1.0:
        logger.info("🎊 SUCCESS: Fragmentation was TRIGGERED (Duration > 1s)")
    else:
        logger.warning("⚠️ Warning: Execution was fast. Check logs to see if fragmentation actually happened.")

    await connector.close()


if __name__ == "__main__":
    asyncio.run(run_validator())
