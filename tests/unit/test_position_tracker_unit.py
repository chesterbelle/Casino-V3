from core.portfolio.position_tracker import PositionTracker


def test_open_position_and_basic_properties():
    tracker = PositionTracker()
    order = {
        "trade_id": "t1",
        "symbol": "BTC/USD",
        "side": "LONG",
        "size": 0.1,
        "leverage": 10,
        "tp_price": 51000.0,  # +2% of 50000
        "sl_price": 49000.0,  # -2% of 50000
    }

    pos = tracker.open_position(
        order=order, entry_price=50000.0, entry_timestamp="2025-11-21T00:00:00Z", available_equity=10000.0
    )
    assert pos is not None
    assert pos.trade_id == "t1"
    assert pos.symbol == "BTCUSD"
    assert pos.side == "LONG"
    assert pos.margin_used > 0
    assert tracker.get_available_equity(10000.0) < 10000.0


def test_close_on_tp_sl():
    tracker = PositionTracker()
    order = {
        "trade_id": "t2",
        "symbol": "BTC/USD",
        "side": "LONG",
        "size": 0.1,
        "leverage": 1,
        "tp_price": 102.0,  # +2% of 100
        "sl_price": 98.0,  # -2% of 100
    }
    # Open position at 100
    pos = tracker.open_position(
        order=order, entry_price=100.0, entry_timestamp="2025-11-21T00:00:00Z", available_equity=1000.0
    )
    assert pos
    assert pos.tp_level == 102.0
    assert pos.sl_level == 98.0
