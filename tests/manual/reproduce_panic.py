import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from core.portfolio.position_tracker import OpenPosition
from croupier.croupier import Croupier

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PanicRepro")


async def reproduce_failure():
    logger.info("🧪 Starting Panic Failure Reproduction...")

    # 1. Mock Components
    mock_adapter = MagicMock()
    mock_tracker = MagicMock()
    mock_oco = MagicMock()

    # 2. Setup Croupier with Real Logic (partial)
    croupier = Croupier(mock_adapter, mock_tracker, mock_oco)

    # Mock internal methods to isolate close_position logic
    croupier.oco_manager.cancel_bracket = AsyncMock()
    croupier.position_tracker._trigger_state_change = MagicMock()

    # Mock Market Order Execution (Simulate delay or failure)
    async def mock_execute_market(order, timeout):
        logger.info(f"⏳ Executing Market Order: {order['symbol']}")
        await asyncio.sleep(0.1)  # Simulate network
        return {"result": "success"}

    croupier.oco_manager._execute_main_order = (
        mock_execute_market  # Direct mock to internal method if possible, or mock executor
    )

    # Actually, close_position calls oco_manager.cancel_bracket then self.executor...
    # Wait, croupier.close_position implementation:
    # 1. Cancel Bracket
    # 2. Execute market close

    # Let's inspect close_position code again. It seems it manually constructs the market order?
    # No, based on previous view_file, it calls something else.
    # We need to trust the logic we saw.

    # Let's mock the internal OCOManager methods used by Croupier if any,
    # OR if Croupier calls adapter directly.
    # Looking at Croupier code (lines 335+):
    # It constructs a `close_side`...
    # But where does it SEND the order?
    # I suspect I missed the actual execution line in Croupier.close_position.

    # Whatever, let's just mock what we know.

    # 3. Create 8 Positions (Mimic the failure scenario)
    positions = []
    for i in range(8):
        pos = OpenPosition(
            trade_id=f"POS_{i}",
            symbol=f"SYM_{i}/USDT",
            side="LONG",
            entry_price=100.0,
            entry_timestamp="2024-01-01",
            margin_used=10.0,
            notional=100.0,
            leverage=1,
            tp_level=110.0,
            sl_level=90.0,
            liquidation_level=0,
            order={"amount": 1.0},
        )
        pos.tp_order_id = f"TP_{i}"
        pos.sl_order_id = f"SL_{i}"
        positions.append(pos)

    croupier.position_tracker.open_positions = positions

    # 4. Trigger Parallel Close (Panic Simulation)
    logger.info("🔥 Triggering Parallel Force Close (Panic Mode)...")

    tasks = []
    for pos in positions:
        # We manually call close_position like ExitManager does
        tasks.append(croupier.close_position(pos.trade_id, exit_reason="DRAIN_PANIC"))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 5. Report Results
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(f"❌ Task {i} Failed: {res}")
        else:
            logger.info(f"✅ Task {i} Success")


if __name__ == "__main__":
    asyncio.run(reproduce_failure())
