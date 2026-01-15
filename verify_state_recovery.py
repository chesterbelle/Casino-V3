import asyncio
import logging
import time

from core.portfolio.position_tracker import OpenPosition, OrderState, PositionTracker
from utils.symbol_norm import normalize_symbol

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StateRecoveryTest")


async def test_state_recovery():
    logger.info("🧪 Starting State Recovery Verification...")

    tracker = PositionTracker()

    # 1. Create a "Restored" Position
    trade_id = "pos_123"
    symbol = "ADA/USDT:USDT"

    pos = OpenPosition(
        trade_id=trade_id,
        symbol=symbol,
        side="LONG",
        entry_price=1.0,
        entry_timestamp=str(int(time.time() * 1000)),
        margin_used=10.0,
        notional=100.0,
        leverage=10.0,
        tp_level=1.1,
        sl_level=0.9,
        liquidation_level=0.5,
        order={"trade_id": trade_id},
        main_order=OrderState(client_order_id="CASINO_MAIN_123", order_type="MAIN", side="LONG"),
        tp_order=OrderState(client_order_id="CASINO_TP_123", order_type="TP", side="SELL"),
        sl_order=OrderState(client_order_id="CASINO_SL_123", order_type="SL", side="SELL"),
    )

    restored_positions = [pos]

    # 2. Perform Restore (The Fix)
    tracker.restore_state(restored_positions)

    # 3. Verify Internal State (The "Amnesia" Test)

    # A. List Presence
    assert len(tracker.open_positions) == 1
    logger.info("✅ Position in main list: PASS")

    # B. Symbol Map Index (Critical for Reconciliation)
    # The symbol in map should be normalized
    norm_sym = normalize_symbol(symbol)  # ADA/USDT
    positions_by_sym = tracker.get_positions_by_symbol(norm_sym)
    assert len(positions_by_sym) == 1
    assert positions_by_sym[0].trade_id == trade_id
    logger.info(f"✅ Position in Symbol Map ({norm_sym}): PASS")

    # C. Alias Map Index (Critical for OCO/Updates)
    # Check Trade ID
    assert tracker.get_position_by_id(trade_id) is not None
    logger.info("✅ Position index by Trade ID: PASS")

    # Check Client IDs
    assert tracker.get_position_by_id("CASINO_TP_123") is not None
    logger.info("✅ Position index by TP Client ID: PASS")

    # 4. Verify Add Position Safety (Adoption Check)
    # If we try to add it again (e.g. during recon), it should handle it gracefully
    tracker.add_position(pos)
    assert len(tracker.open_positions) == 1  # Should not duplicate
    logger.info("✅ Idempotent Add Position: PASS")

    logger.info("🎉 ALL CHECKS PASSED. State Amnesia Bug is FIXED.")


if __name__ == "__main__":
    asyncio.run(test_state_recovery())
