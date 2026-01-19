import asyncio
import logging
import time
import uuid

from core.portfolio.position_tracker import OpenPosition, OrderState, PositionTracker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Simulation")


async def simulate_race_condition():
    tracker = PositionTracker()
    symbol = "BTC/USDT:USDT"

    # The client ID that caused the issue
    target_client_id = f"CASINO_SL_{uuid.uuid4().hex[:12]}"

    # Create the position object correctly
    pos = OpenPosition(
        trade_id="test_trade",
        symbol=symbol,
        side="LONG",
        entry_price=40000.0,
        entry_timestamp=str(time.time()),
        margin_used=100.0,
        notional=40000.0,
        leverage=10.0,
        tp_level=42000.0,
        sl_level=39000.0,
        liquidation_level=35000.0,
        order={},
        sl_order=OrderState(client_order_id=target_client_id, order_type="SL", side="SELL", amount=1.0, price=39000.0),
    )
    tracker.add_position(pos)

    logger.info("--- Simulation Start ---")
    logger.info(f"Target Client ID: {target_client_id}")

    # 1. Pre-register the ID (This is the FIX we just applied)
    # In live code, OCOManager calls this before the exchange request
    tracker.register_alias(target_client_id, pos, symbol=symbol)
    logger.info("✅ Client ID pre-registered in PositionTracker.")

    # 2. Simulate the WebSocket Event arriving
    # This event arrives BEFORE we get the exchange_id back from the request
    ws_event = {
        "s": "BTCUSDT",
        "i": 12345678,  # exchange order id (unknown yet)
        "c": target_client_id,
        "X": "FILLED",
        "S": "SELL",
        "L": "39000.0",
        "l": "1.0",
        "z": "1.0",
        "n": "0.0",
        "N": "USDT",
        "T": int(time.time() * 1000),
    }

    logger.info("📡 Simulating WebSocket event arrival...")
    # handle_order_update should match it via target_client_id and NOT log UNMATCHED
    # We will check if it returns a trade_id (indicating a successful match)
    matched_trade_id = tracker.handle_order_update(ws_event)

    if matched_trade_id == "test_trade":
        logger.info(f"🎉 SUCCESS: Event matched to position {matched_trade_id}")
    else:
        logger.error(f"❌ FAILURE: Event was NOT matched to position (Returned: {matched_trade_id})")


if __name__ == "__main__":
    asyncio.run(simulate_race_condition())
