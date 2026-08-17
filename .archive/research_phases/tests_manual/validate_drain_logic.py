import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DrainValidator")

# Mock configurations
from config import trading

trading.SOFT_EXIT_TP_MULT = 0.5

from core.portfolio.position_tracker import OpenPosition

# Import classes (assuming path is correct)
from croupier.croupier import Croupier


async def test_drain_logic():
    logger.info("🧪 Starting Drain Logic Validation...")

    # 1. Setup Mocks
    mock_adapter = MagicMock()
    mock_tracker = MagicMock()
    mock_oco = MagicMock()

    # 2. Instantiate Croupier & ExitManager
    # We patch the internal components
    croupier = Croupier(mock_adapter, mock_tracker, mock_oco)
    croupier.modify_tp = AsyncMock()
    croupier.close_position = AsyncMock()
    croupier.position_tracker.active_positions = {}

    # 3. Create Dummy Position
    pos = OpenPosition(
        trade_id="TEST_POS_1",
        symbol="BTC/USDT",
        side="LONG",
        entry_price=50000.0,
        entry_timestamp="2024-01-01T00:00:00",
        margin_used=100.0,
        notional=5000.0,
        leverage=1,
        tp_level=51000.0,
        sl_level=49000.0,
        liquidation_level=0,
        order={"origQty": 0.1},
    )
    # Mock initial TP/SL
    pos.tp_order_id = "TP_1"

    # Fix: PositionTracker uses a list 'open_positions'
    croupier.position_tracker.open_positions = [pos]
    croupier.is_drain_mode = True

    # 4. Phase 1: OPTIMISTIC (T-30m)
    # Trigger set_drain_mode manually or just update_drain_status with > 20m
    logger.info("\n--- Testing OPTIMISTIC Phase (T-25m) ---")
    await croupier.update_drain_status(remaining_minutes=25.0)

    # Verify: TP modified to 50% of distance
    # Original Diff = 1000. Target Diff = 500. New TP = 50500.
    croupier.modify_tp.assert_called()
    assert getattr(pos, "drain_phase", "") == "OPTIMISTIC"
    logging.info("✅ OPTIMISTIC Phase Verified")

    # 5. Phase 2: DEFENSIVE (T-15m)
    logger.info("\n--- Testing DEFENSIVE Phase (T-15m) ---")
    await croupier.update_drain_status(remaining_minutes=15.0)

    # Verify: TP modified to Entry (50000)
    args, kwargs = croupier.modify_tp.call_args
    # Args: (trade_id, new_tp_price, symbol, old_tp_order_id)
    assert kwargs["new_tp_price"] == 50000.0
    assert getattr(pos, "drain_phase", "") == "DEFENSIVE"
    logging.info("✅ DEFENSIVE Phase Verified")

    # 6. Phase 3: AGGRESSIVE (T-8m)
    logger.info("\n--- Testing AGGRESSIVE Phase (T-8m) ---")
    await croupier.update_drain_status(remaining_minutes=8.0)

    # Verify: TP modified to -0.1% (49950)
    args, kwargs = croupier.modify_tp.call_args
    assert abs(kwargs["new_tp_price"] - (50000.0 * 0.999)) < 0.01
    assert getattr(pos, "drain_phase", "") == "AGGRESSIVE"
    logging.info("✅ AGGRESSIVE Phase Verified")

    # 7. Phase 4: PANIC (T-2m)
    logger.info("\n--- Testing PANIC Phase (T-2m) ---")
    await croupier.update_drain_status(remaining_minutes=2.0)

    # Verify: Force Close called
    croupier.close_position.assert_called_with("TEST_POS_1", exit_reason="DRAIN_PANIC")
    logging.info("✅ PANIC Phase Verified")

    logger.info("\n🎉 All Drain Phases Validated Successfully!")


if __name__ == "__main__":
    asyncio.run(test_drain_logic())
