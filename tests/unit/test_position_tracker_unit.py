from core.portfolio.position_tracker import PositionTracker


def test_open_position_and_basic_properties():
    tracker = PositionTracker(max_concurrent_positions=2, mode="simulation")
    order = {
        "trade_id": "t1",
        "symbol": "BTC/USD",
        "side": "LONG",
        "size": 0.1,
        "leverage": 10,
        "take_profit": 1.02,
        "stop_loss": 0.98,
    }

    pos = tracker.open_position(
        order=order, entry_price=50000.0, entry_timestamp="2025-11-21T00:00:00Z", available_equity=10000.0
    )
    assert pos is not None
    assert pos.trade_id == "t1"
    assert pos.symbol == "BTC/USD"
    assert pos.side == "LONG"
    assert pos.margin_used > 0
    assert tracker.get_available_equity(10000.0) < 10000.0


def test_simulation_close_on_tp_sl():
    tracker = PositionTracker(mode="simulation")
    order = {
        "trade_id": "t2",
        "symbol": "BTC/USD",
        "side": "LONG",
        "size": 0.1,
        "leverage": 1,
        "take_profit": 1.02,
        "stop_loss": 0.98,
    }
    # Open position at 100
    pos = tracker.open_position(
        order=order, entry_price=100.0, entry_timestamp="2025-11-21T00:00:00Z", available_equity=1000.0
    )
    assert pos

    # Candle that hits TP (high >= TP)
    candle = {"high": 102.0, "low": 99.0, "close": 101.0, "timestamp": "2025-11-21T00:01:00Z"}
    closes = tracker.check_and_close_positions(candle)
    assert len(closes) == 1
    assert closes[0]["exit_reason"] == "TP"

    # Re-open and test SL
    pos2 = tracker.open_position(
        order=order, entry_price=100.0, entry_timestamp="2025-11-21T00:02:00Z", available_equity=1000.0
    )
    candle2 = {"high": 105.0, "low": 97.0, "close": 98.0, "timestamp": "2025-11-21T00:03:00Z"}
    closes2 = tracker.check_and_close_positions(candle2)
    assert len(closes2) == 1
    assert closes2[0]["exit_reason"] == "SL"
