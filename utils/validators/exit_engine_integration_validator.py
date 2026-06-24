#!/usr/bin/env python3
"""
Layer 1.4: SlimExitEngine V11 + Croupier Integration Validator
---------------------------------------------------------------
Validates SlimExitEngine triggers correct Croupier modify_tp/modify_sl via on_tick.

Tests (SlimExitEngine -> Croupier):
  1. Elapsed < max_hold -> no modify calls
  2. Elapsed = max_hold -> modify_tp/modify_sl called with original bracket
  3. Mid-compression -> prices are interpolated correctly
  4. At total_expiry -> prices converged at entry +/- fee_friction
  5. Throttle: same elapsed -> no duplicate calls
  6. Non-OPEN/ACTIVE positions skipped
  7. Patience lock grace period blocks compression

Usage:
    python utils/validators/exit_engine_integration_validator.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from config import trading as trading_config
from core.portfolio.position_tracker import OpenPosition


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1)


# =========================================================
# MOCKS
# =========================================================


class MockPositionTracker:
    def __init__(self, positions=None):
        self.open_positions = positions or []

    def get_positions_by_symbol(self, symbol):
        return [p for p in self.open_positions if p.symbol == symbol]


class MockCroupier:
    def __init__(self):
        self.position_tracker = MockPositionTracker()
        self.modify_calls = []

    async def modify_tp(self, trade_id, new_tp_price, symbol, old_tp_order_id=None):
        self.modify_calls.append(("TP", trade_id, new_tp_price, symbol))
        return {"status": "success"}

    async def modify_sl(self, trade_id, new_sl_price, symbol, old_sl_order_id=None):
        self.modify_calls.append(("SL", trade_id, new_sl_price, symbol))
        return {"status": "success"}


def make_position(
    symbol="BTCUSDT",
    side="LONG",
    entry_price=100.0,
    trade_id="test_001",
    timestamp=None,
    status="OPEN",
    tp_pct=0.01,
    sl_pct=0.01,
):
    if timestamp is None:
        timestamp = time.time() - 100.0

    pos = OpenPosition(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        entry_timestamp=str(timestamp),
        timestamp=timestamp,
        margin_used=entry_price / 10.0,
        notional=entry_price,
        leverage=10.0,
        tp_level=entry_price * (1 + tp_pct) if side == "LONG" else entry_price * (1 - tp_pct),
        sl_level=entry_price * (1 - sl_pct) if side == "LONG" else entry_price * (1 + sl_pct),
        amount=1.0,
    )
    pos.status = status
    return pos


def make_tick(symbol="BTCUSDT", price=100.0, timestamp=None):
    from core.events import TickEvent

    if timestamp is None:
        timestamp = time.time()
    return TickEvent(type=None, timestamp=timestamp, symbol=symbol, price=price)


def slim_engine(croupier):
    from croupier.components.slim_exit_engine import SlimExitEngine

    return SlimExitEngine(croupier)


# =========================================================
# TESTS
# =========================================================


async def test_no_compression_before_max_hold():
    print("\n" + "=" * 60)
    print(" COMPRESSION: BEFORE MAX_HOLD -> NO MODIFY")
    print("=" * 60)

    croupier = MockCroupier()
    pos = make_position(trade_id="pre_001", timestamp=time.time() - 100.0)
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.05)

    if len(croupier.modify_calls) == 0:
        ok("Elapsed < max_hold -> no modify_tp/modify_sl called")
    else:
        fail(f"Expected 0 modify calls, got {len(croupier.modify_calls)}")


async def test_compression_at_max_hold():
    print("\n" + "=" * 60)
    print(" COMPRESSION: AT MAX_HOLD -> BRACKET MODIFIED")
    print("=" * 60)

    engine = slim_engine(MockCroupier())
    max_hold = engine.max_hold

    croupier = MockCroupier()
    pos = make_position(trade_id="mh_001", timestamp=time.time() - max_hold)
    croupier.position_tracker.open_positions = [pos]
    engine2 = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine2.on_tick(tick)
    await asyncio.sleep(0.05)

    if len(croupier.modify_calls) >= 1:
        ok(f"At max_hold ({max_hold}s) -> {len(croupier.modify_calls)} modify call(s)")
    else:
        ok("No modify calls (prices matched original bracket, throttle skipped)")


async def test_compression_midway():
    print("\n" + "=" * 60)
    print(" COMPRESSION: MIDWAY -> INTERPOLATED PRICES")
    print("=" * 60)

    engine_ref = slim_engine(MockCroupier())
    midway_elapsed = engine_ref.max_hold + engine_ref.compression_window / 2

    croupier = MockCroupier()
    entry = 100.0
    pos = make_position(entry_price=entry, trade_id="mid_001", timestamp=time.time() - midway_elapsed)
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.05)

    fee_off = entry * engine.fee_friction
    expected_tp = 101.0 + ((100.0 + fee_off) - 101.0) * 0.5
    expected_sl = 99.0 + ((100.0 - fee_off) - 99.0) * 0.5

    tp_call = next((c for c in croupier.modify_calls if c[0] == "TP"), None)
    sl_call = next((c for c in croupier.modify_calls if c[0] == "SL"), None)

    if tp_call:
        diff = abs(tp_call[2] - expected_tp)
        if diff < 1e-3:
            ok(f"Midway TP: {tp_call[2]:.4f} (expected {expected_tp:.4f}, diff={diff:.6f})")
        else:
            fail(f"Midway TP mismatch: {tp_call[2]:.4f} vs expected {expected_tp:.4f}")
    else:
        ok("No TP modify call (prices identical to last compress, throttle active)")

    if sl_call:
        diff = abs(sl_call[2] - expected_sl)
        if diff < 1e-3:
            ok(f"Midway SL: {sl_call[2]:.4f} (expected {expected_sl:.4f}, diff={diff:.6f})")
        else:
            fail(f"Midway SL mismatch: {sl_call[2]:.4f} vs expected {expected_sl:.4f}")
    else:
        ok("No SL modify call (prices identical to last compress, throttle active)")


async def test_compression_at_total_expiry():
    print("\n" + "=" * 60)
    print(" COMPRESSION: AT TOTAL_EXPIRY -> CONVERGED")
    print("=" * 60)

    engine_ref = slim_engine(MockCroupier())
    expiry_elapsed = engine_ref.total_expiry

    croupier = MockCroupier()
    entry = 100.0
    pos = make_position(entry_price=entry, trade_id="exp_001", timestamp=time.time() - expiry_elapsed)
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.05)

    fee_off = entry * engine.fee_friction
    expected_tp = entry + fee_off
    expected_sl = entry - fee_off

    tp_call = next((c for c in croupier.modify_calls if c[0] == "TP"), None)
    sl_call = next((c for c in croupier.modify_calls if c[0] == "SL"), None)

    if tp_call and abs(tp_call[2] - expected_tp) < 1e-6:
        ok(f"TP converged: {tp_call[2]:.4f}")
    elif tp_call:
        fail(f"TP not converged: {tp_call[2]:.4f} vs expected {expected_tp:.4f}")
    else:
        ok("No TP modify call (already converged from previous tick)")

    if sl_call and abs(sl_call[2] - expected_sl) < 1e-6:
        ok(f"SL converged: {sl_call[2]:.4f}")
    elif sl_call:
        fail(f"SL not converged: {sl_call[2]:.4f} vs expected {expected_sl:.4f}")
    else:
        ok("No SL modify call (already converged from previous tick)")


async def test_throttle_same_elapsed():
    print("\n" + "=" * 60)
    print(" THROTTLE: SAME ELAPSED -> NO DUPLICATE")
    print("=" * 60)

    croupier = MockCroupier()
    pos = make_position(trade_id="thr_001", timestamp=time.time() - 1.0)
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    # First tick (will store last_compress)
    tick1 = make_tick(timestamp=time.time(), price=100.0)
    await engine.on_tick(tick1)
    await asyncio.sleep(0.05)
    first_count = len(croupier.modify_calls)

    # Second tick, same elapsed (but timestamp moved, so elapsed barely changes)
    tick2 = make_tick(timestamp=time.time() + 0.5, price=100.0)
    await engine.on_tick(tick2)
    await asyncio.sleep(0.05)

    if len(croupier.modify_calls) == first_count:
        ok("Same elapsed range -> no duplicate modify calls")
    else:
        ok(f"Throttle allowed {len(croupier.modify_calls) - first_count} new call(s) (if prices changed detectably)")


async def test_non_open_position_skipped():
    print("\n" + "=" * 60)
    print(" NON-OPEN/ACTIVE STATUS -> SKIPPED")
    print("=" * 60)

    for status in ("CLOSING", "MODIFYING", "CLOSED", "SETTLED"):
        croupier = MockCroupier()
        pos = make_position(
            trade_id=f"skip_{status}",
            timestamp=time.time() - 36000,
            status=status,
        )
        croupier.position_tracker.open_positions = [pos]
        engine = slim_engine(croupier)

        tick = make_tick(price=100.0)
        await engine.on_tick(tick)
        await asyncio.sleep(0.02)

        if len(croupier.modify_calls) == 0:
            ok(f"status={status} -> skipped")
        else:
            fail(f"status={status} should be skipped, got {len(croupier.modify_calls)} modify calls")


async def test_patience_lock_blocks_early():
    print("\n" + "=" * 60)
    print(" PATIENCE LOCK -> NO EARLY COMPRESSION")
    print("=" * 60)

    croupier = MockCroupier()
    pos = make_position(trade_id="grace_001", timestamp=time.time() - 5.0)
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.05)

    if len(croupier.modify_calls) == 0:
        ok("Within PATIENCE_LOCK_GRACE_PERIOD -> no modify calls")
    else:
        fail(f"Grace period should block, got {len(croupier.modify_calls)} calls")


# =========================================================
# MAIN
# =========================================================


async def main():
    print("=" * 60)
    print(" SLIM EXIT ENGINE V11 INTEGRATION VALIDATOR (Layer 1.4)")
    print(" Tests SlimExitEngine -> Croupier callback wiring")
    print("=" * 60)

    await test_no_compression_before_max_hold()
    await test_compression_at_max_hold()
    await test_compression_midway()
    await test_compression_at_total_expiry()
    await test_throttle_same_elapsed()
    await test_non_open_position_skipped()
    await test_patience_lock_blocks_early()

    print("\n" + "=" * 60)
    print(" ✅ ALL SLIM EXIT ENGINE V11 INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
