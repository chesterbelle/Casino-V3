import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.clock import Clock
from core.order_tracker import ConfidenceLevel, OrderTracker


@pytest.mark.asyncio
async def test_order_tracker_lifecycle():
    # Setup mock adapter
    adapter = MagicMock()
    adapter.fetch_order = AsyncMock(return_value={"id": "O1", "status": "filled", "symbol": "BTC/USDT"})

    tracker = OrderTracker(adapter, probe_timeout=0.1)
    await tracker.start()

    # 1. Track LOCAL order
    order_data = {"id": "O1", "symbol": "BTC/USDT", "amount": 1.0, "side": "buy", "status": "open"}
    tracker.track_local_order(order_data)

    active = tracker.get_active_orders()
    assert "O1" in active
    assert active["O1"].confidence == ConfidenceLevel.LOCAL

    # 2. WS Update
    ws_event = {"id": "O1", "status": "partially_filled"}
    await tracker.handle_ws_update(ws_event)
    assert tracker._orders["O1"].confidence == ConfidenceLevel.WS
    assert tracker._orders["O1"].status == "partially_filled"

    # 3. Simulate Stale State for another order
    o2_data = {"id": "O2", "symbol": "ETH/USDT", "amount": 2.0, "side": "sell", "status": "open"}
    tracker.track_local_order(o2_data)

    # Mock adapter response for O2
    adapter.fetch_order = AsyncMock(return_value={"id": "O2", "status": "canceled", "symbol": "ETH/USDT"})

    # Wait for timeout
    await asyncio.sleep(0.15)

    # Tick should trigger probe
    await tracker.tick(time.time())

    assert tracker._orders["O2"].confidence == ConfidenceLevel.REST
    assert tracker._orders["O2"].status == "canceled"

    await tracker.stop()


@pytest.mark.asyncio
async def test_order_tracker_clock_integration():
    adapter = MagicMock()
    adapter.fetch_order = AsyncMock(return_value={"id": "O3", "status": "closed", "symbol": "BTC/USDT"})

    tracker = OrderTracker(adapter, probe_timeout=0.05)
    clock = Clock(tick_size_seconds=0.1)
    clock.add_iterator(tracker)

    await clock.start()

    tracker.track_local_order({"id": "O3", "symbol": "BTC/USDT", "status": "open"})

    # Wait for clock to tick and trigger probe
    await asyncio.sleep(0.25)

    assert tracker._orders["O3"].confidence == ConfidenceLevel.REST
    assert tracker._orders["O3"].status == "closed"

    await clock.stop()


@pytest.mark.asyncio
async def test_order_tracker_position_tracking():
    adapter = MagicMock()
    tracker = OrderTracker(adapter)
    await tracker.start()

    # 1. Open Long
    tracker.track_local_order({"id": "O1", "symbol": "BTC/USDT", "side": "buy", "amount": 0.1, "status": "open"})
    await tracker.handle_ws_update({"id": "O1", "status": "FILLED", "price": 50000})

    assert "BTC/USDT" in tracker._positions
    assert tracker._positions["BTC/USDT"].side == "LONG"
    assert tracker._positions["BTC/USDT"].amount == 0.1

    # 2. Add to Long
    tracker.track_local_order({"id": "O2", "symbol": "BTC/USDT", "side": "buy", "amount": 0.1, "status": "open"})
    await tracker.handle_ws_update({"id": "O2", "status": "FILLED", "price": 52000})

    assert tracker._positions["BTC/USDT"].amount == 0.2
    assert tracker._positions["BTC/USDT"].entry_price == 51000  # (50k + 52k) / 2

    # 3. Partially Close
    tracker.track_local_order({"id": "O3", "symbol": "BTC/USDT", "side": "sell", "amount": 0.1, "status": "open"})
    await tracker.handle_ws_update({"id": "O3", "status": "FILLED", "price": 53000})

    assert tracker._positions["BTC/USDT"].amount == 0.1

    # 4. Final Close
    tracker.track_local_order({"id": "O4", "symbol": "BTC/USDT", "side": "sell", "amount": 0.1, "status": "open"})
    await tracker.handle_ws_update({"id": "O4", "status": "FILLED", "price": 54000})

    assert "BTC/USDT" not in tracker._positions

    await tracker.stop()
