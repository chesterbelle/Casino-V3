import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.portfolio.position_tracker import PositionTracker


@pytest.mark.asyncio
async def test_fee_enrichment_logic():
    # 1. Setup Mocks
    mock_adapter = MagicMock()
    mock_adapter.cancel_order = AsyncMock(return_value=True)
    # Mock fetch_my_trades to return a trade with a REAL fee
    mock_adapter.fetch_my_trades = AsyncMock(
        return_value=[
            {
                "id": "trade_1",
                "order": "order_123",
                "symbol": "BTC/USDT",
                "side": "sell",
                "price": 50000.0,
                "qty": 0.1,
                "fee": {"cost": 1.5, "currency": "USDT"},  # Real Fee: 1.5 USDT
                "timestamp": 1234567890,
            }
        ]
    )

    # 2. Initialize Tracker
    tracker = PositionTracker(adapter=mock_adapter)

    # 3. Open a dummy position
    pos = tracker.open_position(
        order={"symbol": "BTC/USDT", "side": "BUY", "size": 0.1, "amount": 0.1},
        entry_price=49000.0,
        entry_timestamp="2024-01-01",
        available_equity=10000.0,
        main_order_id="entry_1",
        tp_order_id="order_123",  # TP order matches the update we will send
        sl_order_id="sl_1",
    )

    assert pos is not None
    assert pos.trade_id is not None
    print(f"Position opened: {pos.trade_id}")

    # 4. Simulate WS Order Update with Fee = 0.0 (The Problem)
    update = {
        "id": "order_123",
        "status": "closed",
        "symbol": "BTC/USDT",
        "side": "sell",
        "price": 50000.0,
        "filled": 0.1,
        "fee": {"cost": 0.0, "currency": "USDT"},  # Zero fee in WS
    }

    print("Simulating WS update with fee=0.0...")
    await tracker.handle_order_update(update)

    # 5. Wait for async task to complete
    # handle_order_update triggers a background task, we need to yield to event loop
    await asyncio.sleep(1.5)

    # 6. Verify Results
    # Check if fetch_my_trades was called
    mock_adapter.fetch_my_trades.assert_called_with("BTC/USDT", limit=5)
    print("✅ fetch_my_trades called!")

    # Check history for recorded fee
    assert len(tracker.history) == 1
    closed_trade = tracker.history[0]

    print(f"Closed Trade Data: {closed_trade}")

    assert closed_trade["fee"] == 1.5, f"Expected fee 1.5, got {closed_trade['fee']}"
    assert closed_trade["pnl"] > 0

    print("✅ Fee correctly enriched to 1.5 USDT!")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(test_fee_enrichment_logic())
