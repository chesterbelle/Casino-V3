#!/usr/bin/env python3
"""
Layer 0.E: SlimExitEngine V11 Compression Math Validator
---------------------------------------------------------
Validates bracket compression math in isolation.

Tests (no real Croupier / SensorManager):
  1. Elapsed < max_hold → no compression
  2. Elapsed = max_hold → TP/SL at original levels (progress=0)
  3. Mid-compression → TP/SL halfway to convergence
  4. At total_expiry → TP/SL converge at entry +/- fee_friction
  5. Throttle: same prices skip modify
  6. Throttle: meaningful change triggers modify
  7. Grace period blocks compression
  8. Non-OPEN/ACTIVE status skipped

Usage:
    python utils/validators/exit_engine_validator.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from config import trading as trading_config
from core.events import TickEvent
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

    async def modify_tp(self, trade_id, new_tp_price, symbol):
        self.modify_calls.append(("TP", trade_id, new_tp_price, symbol))

    async def modify_sl(self, trade_id, new_sl_price, symbol):
        self.modify_calls.append(("SL", trade_id, new_sl_price, symbol))


def make_position(
    symbol="BTCUSDT",
    side="LONG",
    entry_price=100.0,
    trade_id="test_001",
    timestamp=0.0,
    status="OPEN",
    tp_pct=0.01,
    sl_pct=0.01,
):
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


def slim_engine(croupier=None):
    from croupier.components.slim_exit_engine import SlimExitEngine

    return SlimExitEngine(croupier or MockCroupier())


# =========================================================
# TESTS
# =========================================================


async def test_no_compression_before_max_hold():
    print("\n" + "=" * 60)
    print(" COMPRESSION: BEFORE MAX_HOLD")
    print("=" * 60)

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    pos = make_position(entry_price=100.0, timestamp=0.0)

    # elapsed just under max_hold
    await engine._apply_compression(pos, engine.max_hold - 10.0)
    if len(croupier.modify_calls) == 0:
        ok(f"Elapsed < {engine.max_hold}s → no compression")
    else:
        fail(f"Expected 0 modify calls, got {len(croupier.modify_calls)}")


async def test_compression_at_max_hold():
    print("\n" + "=" * 60)
    print(" COMPRESSION: AT MAX_HOLD (PROGRESS=0)")
    print("=" * 60)

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    entry = 100.0
    pos = make_position(entry_price=entry, timestamp=0.0, side="LONG")

    # elapsed = max_hold, progress = 0, TP/SL unchanged
    await engine._apply_compression(pos, engine.max_hold)
    if len(croupier.modify_calls) >= 1:
        tp_call = next((c for c in croupier.modify_calls if c[0] == "TP"), None)
        sl_call = next((c for c in croupier.modify_calls if c[0] == "SL"), None)
        if tp_call and abs(tp_call[2] - pos.tp_level) < 1e-6:
            ok(f"TP at original level {pos.tp_level:.2f} at t=0% compression")
        else:
            fail(f"TP should be at original level, got: {tp_call}")
        if sl_call and abs(sl_call[2] - pos.sl_level) < 1e-6:
            ok(f"SL at original level {pos.sl_level:.2f} at t=0% compression")
        else:
            fail(f"SL should be at original level, got: {sl_call}")
    else:
        ok("No modify calls (throttle may have skipped identical prices)")


async def test_compression_midway():
    print("\n" + "=" * 60)
    print(" COMPRESSION: MIDWAY (PROGRESS=0.5)")
    print("=" * 60)

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    entry = 100.0
    pos = make_position(entry_price=entry, timestamp=0.0, side="LONG")

    elapsed = engine.max_hold + engine.compression_window / 2  # 50% progress
    await engine._apply_compression(pos, elapsed)

    fee_off = entry * engine.fee_friction
    expected_tp = pos.tp_level + ((entry + fee_off) - pos.tp_level) * 0.5
    expected_sl = pos.sl_level + ((entry - fee_off) - pos.sl_level) * 0.5

    tp_call = next((c for c in croupier.modify_calls if c[0] == "TP"), None)
    sl_call = next((c for c in croupier.modify_calls if c[0] == "SL"), None)
    if tp_call and abs(tp_call[2] - expected_tp) < 1e-4:
        ok(f"TP at 50% compression: {tp_call[2]:.4f} (expected {expected_tp:.4f})")
    else:
        fail(f"TP midway mismatch: got {tp_call}, expected {expected_tp:.4f}")
    if sl_call and abs(sl_call[2] - expected_sl) < 1e-4:
        ok(f"SL at 50% compression: {sl_call[2]:.4f} (expected {expected_sl:.4f})")
    else:
        fail(f"SL midway mismatch: got {sl_call}, expected {expected_sl:.4f}")


async def test_compression_at_total_expiry():
    print("\n" + "=" * 60)
    print(" COMPRESSION: AT TOTAL_EXPIRY (PROGRESS=1.0)")
    print("=" * 60)

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    entry = 100.0
    pos = make_position(entry_price=entry, timestamp=0.0, side="LONG")

    await engine._apply_compression(pos, engine.total_expiry)

    fee_off = entry * engine.fee_friction
    expected_tp = entry + fee_off
    expected_sl = entry - fee_off

    tp_call = next((c for c in croupier.modify_calls if c[0] == "TP"), None)
    sl_call = next((c for c in croupier.modify_calls if c[0] == "SL"), None)
    if tp_call and abs(tp_call[2] - expected_tp) < 1e-6:
        ok(f"TP converged at entry + fee: {tp_call[2]:.4f} (expected {expected_tp:.4f})")
    else:
        fail(f"TP convergence mismatch: got {tp_call}, expected {expected_tp:.4f}")
    if sl_call and abs(sl_call[2] - expected_sl) < 1e-6:
        ok(f"SL converged at entry - fee: {sl_call[2]:.4f} (expected {expected_sl:.4f})")
    else:
        fail(f"SL convergence mismatch: got {sl_call}, expected {expected_sl:.4f}")


async def test_compression_short_side():
    print("\n" + "=" * 60)
    print(" COMPRESSION: SHORT SIDE")
    print("=" * 60)

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    entry = 100.0
    pos = make_position(entry_price=entry, timestamp=0.0, side="SHORT")

    await engine._apply_compression(pos, engine.total_expiry)

    fee_off = entry * engine.fee_friction
    expected_tp = entry - fee_off  # TP below entry for SHORT
    expected_sl = entry + fee_off  # SL above entry for SHORT

    tp_call = next((c for c in croupier.modify_calls if c[0] == "TP"), None)
    sl_call = next((c for c in croupier.modify_calls if c[0] == "SL"), None)
    if tp_call and abs(tp_call[2] - expected_tp) < 1e-6:
        ok(f"SHORT TP converged at entry - fee: {tp_call[2]:.4f}")
    else:
        fail(f"SHORT TP convergence mismatch: got {tp_call}, expected {expected_tp:.4f}")
    if sl_call and abs(sl_call[2] - expected_sl) < 1e-6:
        ok(f"SHORT SL converged at entry + fee: {sl_call[2]:.4f}")
    else:
        fail(f"SHORT SL convergence mismatch: got {sl_call}, expected {expected_sl:.4f}")


async def test_throttle_no_duplicate():
    print("\n" + "=" * 60)
    print(" THROTTLE: SAME PRICE → SKIP")
    print("=" * 60)

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    pos = make_position(entry_price=100.0, timestamp=0.0)

    await engine._apply_compression(pos, engine.max_hold)
    first_calls = len(croupier.modify_calls)

    # Same elapsed → same prices → should throttle
    await engine._apply_compression(pos, engine.max_hold)
    if len(croupier.modify_calls) == first_calls:
        ok("Duplicate elapsed → no redundant modify calls")
    else:
        fail(f"Expected {first_calls} calls (no change), got {len(croupier.modify_calls)}")


async def test_throttle_triggers_on_change():
    print("\n" + "=" * 60)
    print(" THROTTLE: PRICE CHANGE → TRIGGER")
    print("=" * 60)

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    pos = make_position(entry_price=100.0, timestamp=0.0)

    await engine._apply_compression(pos, engine.max_hold)
    first_calls = len(croupier.modify_calls)

    # Different elapsed → meaningfully different prices → should trigger
    elapsed = engine.max_hold + engine.compression_window / 2
    await engine._apply_compression(pos, elapsed)
    if len(croupier.modify_calls) > first_calls:
        ok("Progress change → new modify calls issued")
    else:
        fail(f"Expected more calls after progress change, got {len(croupier.modify_calls)}")


async def test_grace_period_blocks():
    print("\n" + "=" * 60)
    print(" GRACE PERIOD → NO COMPRESSION")
    print("=" * 60)

    grace = getattr(trading_config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0)
    croupier = MockCroupier()
    pos = make_position(trade_id="grace_001", timestamp=time.time() - 5.0)
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = TickEvent(type=None, timestamp=time.time(), symbol="BTCUSDT", price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.05)

    if len(croupier.modify_calls) == 0:
        ok(f"Elapsed < {grace}s → patience lock blocks compression")
    else:
        fail("Patience lock should block compression during grace period")


async def test_non_open_status_skipped():
    print("\n" + "=" * 60)
    print(" NON-OPEN/ACTIVE STATUS → SKIPPED")
    print("=" * 60)

    for status in ("CLOSING", "CLOSE_FAILED", "SETTLED", "CLOSED", "OFF_BOARDING"):
        croupier = MockCroupier()
        pos = make_position(
            trade_id=f"stat_{status}",
            timestamp=time.time() - 36000,  # well past total_expiry
            status=status,
        )
        croupier.position_tracker.open_positions = [pos]
        engine = slim_engine(croupier)

        tick = TickEvent(type=None, timestamp=time.time(), symbol="BTCUSDT", price=100.0)
        await engine.on_tick(tick)
        await asyncio.sleep(0.02)

        if len(croupier.modify_calls) == 0:
            ok(f"status={status} → skipped")
        else:
            fail(f"status={status} should be skipped, got {len(croupier.modify_calls)} modify calls")


# =========================================================
# MAIN
# =========================================================


async def main():
    print("=" * 60)
    print(" SLIM EXIT ENGINE V11 VALIDATOR (Layer 0.E)")
    print(" Tests bracket compression math in isolation")
    print("=" * 60)

    await test_no_compression_before_max_hold()
    await test_compression_at_max_hold()
    await test_compression_midway()
    await test_compression_at_total_expiry()
    await test_compression_short_side()
    await test_throttle_no_duplicate()
    await test_throttle_triggers_on_change()
    await test_grace_period_blocks()
    await test_non_open_status_skipped()

    print("\n" + "=" * 60)
    print(" ✅ ALL SLIM EXIT ENGINE V11 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
