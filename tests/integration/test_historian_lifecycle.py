import asyncio
import sqlite3
import time

import pytest

from core.observability.historian import TradeHistorian


@pytest.fixture
def memory_historian():
    """Create an in-memory historian for testing."""
    historian = TradeHistorian(db_path=":memory:")
    yield historian
    historian.stop()


def test_trade_lifecycle_event_sourcing(memory_historian):
    """Test that lifecycle events are correctly recorded in order."""
    trade_id = "test_trade_lifecycle_123"

    # 1. Emit several lifecycle events
    memory_historian.record_lifecycle_event(trade_id, "ORDER_SUBMITTED", "Main order sent to exchange")
    time.sleep(0.01)  # Ensure timestamp ordering
    memory_historian.record_lifecycle_event(trade_id, "FILLED", "Main order filled at 50000")
    time.sleep(0.01)
    memory_historian.record_lifecycle_event(trade_id, "BRACKET_CREATED", "OCO bracket established")

    # 2. Query the database directly to verify
    with memory_historian._get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT event_type, details FROM trade_lifecycle_events WHERE trade_id = ? ORDER BY timestamp ASC",
            (trade_id,),
        )
        events = cursor.fetchall()

    # 3. Assertions
    assert len(events) == 3

    assert events[0][0] == "ORDER_SUBMITTED"
    assert events[0][1] == "Main order sent to exchange"

    assert events[1][0] == "FILLED"
    assert events[1][1] == "Main order filled at 50000"

    assert events[2][0] == "BRACKET_CREATED"
    assert events[2][1] == "OCO bracket established"


def test_pending_orphan_check_registration(memory_historian):
    """Test registering and resolving pending orphans."""
    trade_id = "orphan_test_1"

    # Register pending orphan
    success = memory_historian.register_pending_orphan(
        trade_id=trade_id,
        client_order_id="client_123",
        symbol="BTC/USDT",
        side="LONG",
        amount=1.0,
        expected_entry_price=50000.0,
        notes="Timeout during OCO",
    )
    assert success is True

    # Fetch pending orphans (older than 0 seconds to catch it immediately)
    orphans = memory_historian.fetch_pending_orphans(older_than_seconds=-1.0)
    assert len(orphans) == 1
    assert orphans[0]["trade_id"] == trade_id
    assert orphans[0]["outcome"] is None

    # Resolve pending orphan
    resolve_success = memory_historian.resolve_pending_orphan(
        trade_id=trade_id, outcome="FILLED", recovered_amount=1.0, recovered_entry_price=50000.0
    )
    assert resolve_success is True

    # Fetch again, should be empty because it is resolved
    orphans_after = memory_historian.fetch_pending_orphans(older_than_seconds=-1.0)
    assert len(orphans_after) == 0

    # Query raw DB to verify resolution data
    with memory_historian._get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT outcome, recovered_amount FROM pending_orphan_check WHERE trade_id = ?", (trade_id,))
        row = cursor.fetchone()

    assert row[0] == "FILLED"
    assert row[1] == 1.0
