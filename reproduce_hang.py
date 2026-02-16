import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

# Import actual components
from croupier.croupier import Croupier
from exchanges.adapters.exchange_adapter import ExchangeAdapter

# Setup rudimentary logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Reproduction")


async def reproduce():
    logger.info("🚀 Starting Repro Script (Attempt 3)")

    # 1. Mock Adapter (Wrapper)
    # We mock the ADAPTER directly to avoid internal logic issues
    adapter = MagicMock(spec=ExchangeAdapter)
    adapter.symbol = "BTCUSDT"
    adapter.is_congested = False  # Force safe

    # Mock synchronous methods to return clean values
    adapter.amount_to_precision.return_value = "1.00000"
    adapter.price_to_precision.return_value = "100.00"
    adapter.normalize_symbol.side_effect = lambda s: s

    # Mock async methods
    adapter.get_current_price = AsyncMock(return_value=100.0)
    adapter.fetch_ticker = AsyncMock(return_value={"last": 100.0})
    adapter.fetch_balance = AsyncMock(return_value={"free": 1000.0, "locked": 0.0})

    # MOCK THE HANG:
    # Scenario 1: execute_order succeeds instantly with "open"
    # Scenario 2: fetch_order hangs (Polling Loop Vulnerability)

    async def mock_execute_order(*args, **kwargs):
        logger.info("✅ Mock Adapter: Order placed instantly (Status: OPEN)")
        return {"status": "open", "order_id": "123", "symbol": "BTCUSDT"}

    adapter.execute_order = AsyncMock(side_effect=mock_execute_order)

    async def mock_fetch_order(*args, **kwargs):
        logger.info("😈 Mock Adapter: Hanging indefinitely... (inside fetch_order)")
        await asyncio.sleep(3600)
        return {"status": "filled"}

    adapter.fetch_order = AsyncMock(side_effect=mock_fetch_order)

    # 2. Setup Croupier
    croupier = Croupier(adapter, initial_balance=1000.0)

    # instrument oco_manager to fail fast if it works
    order_params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "amount": 1.0,
        "take_profit": 0.01,
        "stop_loss": 0.01,
        "trade_id": "test_hang",
        "t0_signal_ts": 1234567890,
    }

    logger.info("📥 Executing Order (Expect Timeout in 5s)...")
    start_time = asyncio.get_event_loop().time()

    try:
        # We wrap in a generic timeout just so the script doesn't hang forever if the bug exists
        # Expected duration: 3 retries * (2.0s timeout + 0.5s sleep) = 7.5s
        # Plus execution overhead.
        await asyncio.wait_for(croupier.execute_order(order_params), timeout=9.0)
    except asyncio.TimeoutError:
        logger.error("❌ SCRIPT TIMEOUT: The code hung for >9s! Fix might be insufficient!")
        return
    except Exception as e:
        logger.info(f"✅ Execpted Exception caught: {e}")

    duration = asyncio.get_event_loop().time() - start_time
    logger.info(f"⏱️ Duration: {duration:.2f}s")

    if 7.0 <= duration < 8.5:
        logger.info("✅ SUCCESS: Polling timeout logic worked (3 retries limited to ~7.5s).")
    elif duration < 7.0:
        logger.warning(f"⚠️ FAST FAIL: Duration {duration:.2f}s is < 7.5s. Did it skip retries?")
    else:
        logger.warning(f"⚠️ SLOW FAIL: Duration {duration:.2f}s is > 8.5s. Overhead is high.")


if __name__ == "__main__":
    asyncio.run(reproduce())
