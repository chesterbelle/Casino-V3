#!/usr/bin/env python3
"""
Layer 0.E: SlimExitEngine Pillar Math Validator (Universal)
----------------------------------------------------------
Validates each SlimExitEngine pillar computes correct exit decisions in isolation.

Tests (no real Croupier / SensorManager):
  1. Pillar 3: Micro-Z Reversal (abs ΔZ)
  2. Pillar 1: Time Decay
  3. Pillar 2: Break Even
  4. Patience lock grace period skips tactical processing

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
        self.modify_sl_calls = []

    async def close_position(self, trade_id, exit_reason="", prefer_maker=False):
        self.close_calls.append((trade_id, exit_reason, prefer_maker))

    async def modify_sl(self, trade_id, new_sl_price, symbol):
        self.modify_sl_calls.append((trade_id, new_sl_price, symbol))


def make_position(
    symbol="BTCUSDT",
    side="LONG",
    entry_price=100.0,
    trade_id="test_001",
    timestamp=0.0,
    entry_atr=1.0,
    entry_z=None,
    be_activated=False,
    shadow_sl_level=None,
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
        tp_level=entry_price * 1.01,
        sl_level=entry_price * 0.99,
        amount=1.0,
    )
    pos.entry_atr = entry_atr
    pos.be_activated = be_activated
    pos.shadow_sl_level = shadow_sl_level
    if entry_z is not None:
        pos.entry_z = entry_z
    return pos


def slim_engine(croupier=None):
    from croupier.components.slim_exit_engine import SlimExitEngine

    return SlimExitEngine(croupier or MockCroupier())


# =========================================================
# TESTS
# =========================================================


async def test_micro_z_reversal():
    print("\n" + "=" * 60)
    print(" PILAR 3: MICRO-Z REVERSAL (abs ΔZ)")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    threshold = rules["micro_z_reversal"]["threshold"]

    # LONG: entry_z=-3, abs(current_z - entry_z) > threshold
    ctx = MockContextRegistry(z=-3.0 + threshold + 1.0)
    croupier = MockCroupier(context_registry=ctx)
    engine = slim_engine(croupier)
    pos = make_position(side="LONG", entry_z=-3.0)
    triggered = engine._check_micro_z_reversal(pos)
    if triggered and pos.trade_id in engine._pending_terminations:
        ok(f"LONG abs(ΔZ) > {threshold} → invalidation + pending termination")
    else:
        fail("LONG Micro-Z reversal should trigger")
    engine._pending_terminations.discard(pos.trade_id)

    # SHORT: entry_z=+3, abs(current_z - entry_z) > threshold (ΔZ negative but abs > thresh)
    ctx2 = MockContextRegistry(z=3.0 - threshold - 1.0)
    croupier2 = MockCroupier(context_registry=ctx2)
    engine2 = slim_engine(croupier2)
    pos2 = make_position(side="SHORT", entry_z=3.0)
    triggered2 = engine2._check_micro_z_reversal(pos2)
    if triggered2:
        ok(f"SHORT abs(ΔZ) > {threshold} → invalidation")
    else:
        fail("SHORT Micro-Z reversal should trigger")

    # LONG: No reversal when within threshold
    ctx3 = MockContextRegistry(z=-3.0 + 0.5)  # ΔZ = 0.5 < threshold
    croupier3 = MockCroupier(context_registry=ctx3)
    engine3 = slim_engine(croupier3)
    pos3 = make_position(side="LONG", entry_z=-3.0)
    if not engine3._check_micro_z_reversal(pos3):
        ok(f"LONG abs(ΔZ) < {threshold} → no invalidation")
    else:
        fail("LONG Micro-Z should NOT trigger (within threshold)")

    # SHORT: No reversal when within threshold
    ctx4 = MockContextRegistry(z=3.0 - 0.5)  # ΔZ = -0.5, abs=0.5 < threshold
    croupier4 = MockCroupier(context_registry=ctx4)
    engine4 = slim_engine(croupier4)
    pos4 = make_position(side="SHORT", entry_z=3.0)
    if not engine4._check_micro_z_reversal(pos4):
        ok("abs(ΔZ) within threshold → no invalidation")
    else:
        fail("Small abs(ΔZ) should not invalidate")


async def test_time_decay():
    print("\n" + "=" * 60)
    print(" PILAR 1: TIME DECAY")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    max_hold = rules["time_decay"]["max_hold_seconds"]

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    pos = make_position(trade_id="td_001")

    # Inside max hold limit
    triggered = engine._check_time_decay(pos, max_hold - 10.0)
    if not triggered:
        ok("Elapsed < max_hold → hold position")
    else:
        fail("Should not trigger time decay before max_hold_seconds")

    # Exceeding max hold limit
    triggered2 = engine._check_time_decay(pos, max_hold + 10.0)
    if triggered2 and pos.trade_id in engine._pending_terminations:
        ok(f"Elapsed > {max_hold}s → time decay triggered")
    else:
        fail("Should trigger time decay when exceeding limit")


async def test_break_even():
    print("\n" + "=" * 60)
    print(" PILAR 2: BREAK EVEN")
    print("=" * 60)

    rules = trading_config.UNIVERSAL_EXIT_RULES
    trigger_pct = rules["break_even"]["trigger_pct"]
    fee_friction = rules["break_even"]["fee_friction"]

    croupier = MockCroupier()
    engine = slim_engine(croupier)
    pos = make_position(side="LONG", entry_price=100.0)
    tp_pct = 0.01  # 1% TP from tp_level (101.0) vs entry_price (100.0)

    # 1. Trigger threshold not met (below 50% of TP target)
    pnl_unmet_price = 100.0 + (100.0 * tp_pct * trigger_pct * 0.8)
    triggered = engine._check_break_even(pos, pnl_unmet_price)
    if not triggered and not engine._pillar_state.get(pos.trade_id, {}).get("breakeven_activated", False):
        ok("Trigger pct not met → BE not activated")
    else:
        fail("BE should not activate yet")

    # 2. Trigger threshold met (at 50% of TP target)
    pnl_met_price = 100.0 + (100.0 * tp_pct * trigger_pct)
    triggered2 = engine._check_break_even(pos, pnl_met_price)
    state = engine._pillar_state.get(pos.trade_id, {})
    expected_be_price = 100.0 * (1 + fee_friction)
    if (
        not triggered2
        and state.get("breakeven_activated", False)
        and abs(state.get("breakeven_price", 0.0) - expected_be_price) < 1e-5
    ):
        ok(f"Trigger pct met → BE activated at {expected_be_price:.4f}")
    else:
        fail("BE should be activated but not triggered exit yet")

    # 3. Price drops to BE level
    triggered3 = engine._check_break_even(pos, expected_be_price - 0.01)
    if triggered3 and pos.trade_id in engine._pending_terminations:
        ok("Price hit BE level → BREAK_EVEN exit triggered")
    else:
        fail("Price hitting BE should trigger exit")


async def test_on_tick_grace_and_pending():
    print("\n" + "=" * 60)
    print(" ON_TICK: GRACE PERIOD & PENDING GUARD")
    print("=" * 60)

    grace = getattr(trading_config, "PATIENCE_LOCK_GRACE_PERIOD", 15.0)

    # Grace period — no tactical action
    ctx = MockContextRegistry(z=0.0)
    croupier = MockCroupier(context_registry=ctx)
    pos = make_position(side="LONG", entry_z=-3.0, timestamp=time.time() - 5.0)
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)
    tick = TickEvent(type=None, timestamp=time.time(), symbol="BTCUSDT", price=120.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.05)
    if len(croupier.close_calls) == 0:
        ok(f"Elapsed < {grace}s → pillars skipped (patience lock)")
    else:
        fail("Patience lock should block tactical exits")

    # Pending terminations — position skipped
    croupier2 = MockCroupier(context_registry=ctx)
    pos2 = make_position(
        side="LONG",
        entry_z=-3.0,
        timestamp=time.time() - grace - 10.0,
        trade_id="pending_001",
    )
    croupier2.position_tracker.open_positions = [pos2]
    engine2 = slim_engine(croupier2)
    engine2._pending_terminations.add("pending_001")
    tick2 = TickEvent(type=None, timestamp=time.time(), symbol="BTCUSDT", price=120.0)
    await engine2.on_tick(tick2)
    await asyncio.sleep(0.05)
    if len(croupier2.close_calls) == 0:
        ok("_pending_terminations → position skipped in on_tick")
    else:
        fail("Position in _pending_terminations should not be processed")


# =========================================================
# MAIN
# =========================================================


async def main():
    print("=" * 60)
    print(" SLIM EXIT ENGINE VALIDATOR (Layer 0.E) - Universal")
    print(" Tests each pillar's math independently")
    print("=" * 60)

    await test_micro_z_reversal()
    await test_time_decay()
    await test_break_even()
    await test_on_tick_grace_and_pending()

    print("\n" + "=" * 60)
    print(" ✅ ALL SLIM EXIT ENGINE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
