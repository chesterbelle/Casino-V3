#!/usr/bin/env python3
"""
Layer 1.4: SlimExitEngine + Croupier Integration Validator (Universal)
----------------------------------------------------------------------
Validates SlimExitEngine triggers the correct Croupier callbacks via on_tick.

Tests (SlimExitEngine ↔ Croupier):
  1. Micro-Z Reversal → close_position(MZ_REVERSAL, prefer_maker=True)
  2. Time Decay → close_position(TIME_DECAY, prefer_maker=True)
  3. Break Even → close_position(BREAK_EVEN, prefer_maker=True)
  4. Pillar priority: Time Decay blocks Break-Even on the same tick
  5. Non-OPEN positions skipped
  6. Patience lock grace period blocks early tactical exits

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


class MockContextRegistry:
    def __init__(self, z=0.0):
        self._z = z

    def get_micro_state(self, symbol):
        return (0.0, 0.5, self._z)


class MockPositionTracker:
    def __init__(self, positions=None):
        self.open_positions = positions or []

    def get_positions_by_symbol(self, symbol):
        return [p for p in self.open_positions if p.symbol == symbol]


class MockCroupier:
    def __init__(self, context_registry=None):
        self.context_registry = context_registry
        self.position_tracker = MockPositionTracker()
        self.close_calls = []

    async def close_position(self, trade_id, exit_reason="", prefer_maker=False):
        self.close_calls.append((trade_id, exit_reason, prefer_maker))


def make_position(
    symbol="BTCUSDT",
    side="LONG",
    entry_price=100.0,
    trade_id="test_001",
    timestamp=None,
    entry_z=None,
    status="OPEN",
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
        tp_level=entry_price * 1.01,
        sl_level=entry_price * 0.99,
        amount=1.0,
    )
    pos.status = status
    if entry_z is not None:
        pos.entry_z = entry_z
    return pos


def make_tick(symbol="BTCUSDT", price=100.0, timestamp=None):
    from core.events import TickEvent

    if timestamp is None:
        timestamp = time.time()
    return TickEvent(type=None, timestamp=timestamp, symbol=symbol, price=price)


def slim_engine(croupier):
    from croupier.components.slim_exit_engine import SlimExitEngine

    return SlimExitEngine(croupier)


def past_grace_timestamp():
    grace = getattr(trading_config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0)
    return time.time() - grace - 10.0


# =========================================================
# TESTS
# =========================================================


async def test_micro_z_reversal_triggers_close():
    print("\n" + "=" * 60)
    print(" MICRO-Z REVERSAL → CROUPIER CLOSE")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    threshold = rules["micro_z_reversal"]["threshold"]
    entry_z = -3.0
    ctx = MockContextRegistry(z=entry_z + threshold + 2.0)

    croupier = MockCroupier(context_registry=ctx)
    pos = make_position(
        side="LONG",
        entry_z=entry_z,
        trade_id="zs_001",
        timestamp=past_grace_timestamp(),
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.15)

    found = any(
        tid == "zs_001" and reason == "MZ_REVERSAL" and prefer_maker
        for tid, reason, prefer_maker in croupier.close_calls
    )
    if found:
        ok("Micro-Z reversal → close_position(MZ_REVERSAL, prefer_maker=True)")
    else:
        fail(f"Expected MZ close, got: {croupier.close_calls}")


async def test_time_decay_triggers_close():
    print("\n" + "=" * 60)
    print(" TIME DECAY → CROUPIER CLOSE")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    max_hold = rules["time_decay"]["max_hold_seconds"]

    croupier = MockCroupier()
    # Position entered longer than max_hold_seconds ago
    pos = make_position(
        trade_id="td_001",
        timestamp=time.time() - max_hold - 10.0,
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.15)

    found = any(
        tid == "td_001" and reason == "TIME_DECAY" and prefer_maker
        for tid, reason, prefer_maker in croupier.close_calls
    )
    if found:
        ok("Time decay → close_position(TIME_DECAY, prefer_maker=True)")
    else:
        fail(f"Expected TIME_DECAY close, got: {croupier.close_calls}")


async def test_break_even_triggers_close():
    print("\n" + "=" * 60)
    print(" BREAK EVEN → CROUPIER CLOSE")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    trigger_pct = rules["break_even"]["trigger_pct"]
    fee_friction = rules["break_even"]["fee_friction"]

    croupier = MockCroupier()
    pos = make_position(
        trade_id="be_001",
        side="LONG",
        entry_price=100.0,
        timestamp=past_grace_timestamp(),
    )
    tp_pct = 0.01
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    # 1. Trigger the BE activation (at 50% TP target)
    pnl_met_price = 100.0 + (100.0 * tp_pct * trigger_pct)
    await engine.on_tick(make_tick(price=pnl_met_price))
    await asyncio.sleep(0.05)

    # 2. Trigger the BE close (price drops to BE level)
    be_price = 100.0 * (1 + fee_friction)
    await engine.on_tick(make_tick(price=be_price - 0.01))
    await asyncio.sleep(0.15)

    found = any(
        tid == "be_001" and reason == "BREAK_EVEN" and prefer_maker
        for tid, reason, prefer_maker in croupier.close_calls
    )
    if found:
        ok("Break-even hit → close_position(BREAK_EVEN, prefer_maker=True)")
    else:
        fail(f"Expected BREAK_EVEN close, got: {croupier.close_calls}")


async def test_pillar_priority_single_tick():
    print("\n" + "=" * 60)
    print(" PILLAR PRIORITY → ONE ACTION PER TICK")
    print("=" * 60)

    # Time Decay has priority over Break Even
    rules = trading_config.UNIVERSAL_EXIT_RULES
    max_hold = rules["time_decay"]["max_hold_seconds"]
    fee_friction = rules["break_even"]["fee_friction"]

    croupier = MockCroupier()
    # Trigger time decay by having old timestamp
    pos = make_position(
        trade_id="prio_001",
        side="LONG",
        entry_price=100.0,
        timestamp=time.time() - max_hold - 10.0,
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    # Set state as breakeven already activated
    be_price = 100.0 * (1 + fee_friction)
    engine._pillar_state["prio_001"] = {
        "breakeven_activated": True,
        "breakeven_price": be_price,
    }

    # Tick at BE price to trigger Break Even, while Time Decay is also triggered
    await engine.on_tick(make_tick(price=be_price - 0.01))
    await asyncio.sleep(0.15)

    # Since Time Decay is evaluated first, it should close via TIME_DECAY and stop tick evaluation
    closes = croupier.close_calls
    if len(closes) == 1 and closes[0][1] == "TIME_DECAY":
        ok("Time decay fires; break-even skipped on same tick (pillar priority)")
    else:
        fail(f"Expected 1 TIME_DECAY close and 0 break-evens, got closes={closes}")


async def test_non_open_position_skipped():
    print("\n" + "=" * 60)
    print(" NON-OPEN POSITION → SKIPPED")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    threshold = rules["micro_z_reversal"]["threshold"]
    entry_z = -3.0
    ctx = MockContextRegistry(z=entry_z + threshold + 2.0)

    croupier = MockCroupier(context_registry=ctx)
    pos = make_position(
        side="LONG",
        entry_z=entry_z,
        trade_id="closed_001",
        timestamp=past_grace_timestamp(),
        status="CLOSING",
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.1)

    if not croupier.close_calls:
        ok("status != OPEN → no Croupier exit callbacks")
    else:
        fail(f"CLOSING position should be skipped, got closes={croupier.close_calls}")


async def test_patience_lock_blocks_early_exit():
    print("\n" + "=" * 60)
    print(" PATIENCE LOCK → NO EARLY TACTICAL EXIT")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    threshold = rules["micro_z_reversal"]["threshold"]
    entry_z = -3.0
    ctx = MockContextRegistry(z=entry_z + threshold + 2.0)

    croupier = MockCroupier(context_registry=ctx)
    pos = make_position(
        side="LONG",
        entry_z=entry_z,
        trade_id="grace_001",
        timestamp=time.time() - 5.0,
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.1)

    if not croupier.close_calls:
        ok("Within PATIENCE_LOCK_GRACE_PERIOD → no close_position")
    else:
        fail(f"Grace period should block exits, got: {croupier.close_calls}")


# =========================================================
# MAIN
# =========================================================


async def main():
    print("=" * 60)
    print(" SLIM EXIT ENGINE INTEGRATION VALIDATOR (Layer 1.4) - Universal")
    print(" Tests SlimExitEngine → Croupier callback wiring")
    print("=" * 60)

    await test_micro_z_reversal_triggers_close()
    await test_time_decay_triggers_close()
    await test_break_even_triggers_close()
    await test_pillar_priority_single_tick()
    await test_non_open_position_skipped()
    await test_patience_lock_blocks_early_exit()

    print("\n" + "=" * 60)
    print(" ✅ ALL SLIM EXIT ENGINE INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
