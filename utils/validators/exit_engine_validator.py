#!/usr/bin/env python3
"""
Layer 0.E: SlimExitEngine Pillar Math Validator
------------------------------------------------
Validates each SlimExitEngine pillar computes correct exit decisions in isolation.

Tests (no real Croupier / SensorManager):
  1. Profile resolution (BLUE_CHIP vs DEFAULT fallback)
  2. Pillar 4: Micro-Z Reversal
  3. Pillar 1: Scale-out at ATR target
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
        self.scale_out_calls = []
        self.modify_sl_calls = []

    async def close_position(self, trade_id, exit_reason="", prefer_maker=False):
        self.close_calls.append((trade_id, exit_reason, prefer_maker))

    async def scale_out_structural(self, trade_id, fraction=0.5, reason=""):
        self.scale_out_calls.append((trade_id, fraction, reason))

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
    scaled_out=False,
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
    pos.scaled_out = scaled_out
    pos.be_activated = be_activated
    pos.shadow_sl_level = shadow_sl_level
    if entry_z is not None:
        pos.entry_z = entry_z
    return pos


def blue_chip_profile():
    return trading_config.ASSET_EXIT_PROFILES["BLUE_CHIP"]


def slim_engine(croupier=None):
    from croupier.components.slim_exit_engine import SlimExitEngine

    return SlimExitEngine(croupier or MockCroupier())


# =========================================================
# TESTS
# =========================================================


def test_profile_resolution():
    print("\n" + "=" * 60)
    print(" PROFILE RESOLUTION")
    print("=" * 60)

    engine = slim_engine()
    profile = engine._get_profile("BTC/USDT")
    if profile is trading_config.ASSET_EXIT_PROFILES["BLUE_CHIP"]:
        ok("BTC/USDT → BLUE_CHIP profile")
    else:
        fail("BTC/USDT should resolve to BLUE_CHIP")

    default = engine._get_profile("UNKNOWNCOIN")
    if default is trading_config.ASSET_EXIT_PROFILES["DEFAULT"]:
        ok("Unknown symbol → DEFAULT profile")


async def test_micro_z_reversal():
    print("\n" + "=" * 60)
    print(" PILAR 4: MICRO-Z REVERSAL (abs ΔZ)")
    print("=" * 60)

    profile = blue_chip_profile()
    threshold = profile["micro_z_reversal"]["threshold"]

    # LONG: entry_z=-3, abs(current_z - entry_z) > threshold
    ctx = MockContextRegistry(z=-3.0 + threshold + 1.0)
    croupier = MockCroupier(context_registry=ctx)
    engine = slim_engine(croupier)
    pos = make_position(side="LONG", entry_z=-3.0)
    triggered = engine._check_micro_z_reversal(pos, profile)
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
    triggered2 = engine2._check_micro_z_reversal(pos2, profile)
    if triggered2:
        ok(f"SHORT abs(ΔZ) > {threshold} → invalidation")
    else:
        fail("SHORT Micro-Z reversal should trigger")

    # LONG: No reversal when within threshold
    ctx3 = MockContextRegistry(z=-3.0 + 0.5)  # ΔZ = 0.5 < threshold
    croupier3 = MockCroupier(context_registry=ctx3)
    engine3 = slim_engine(croupier3)
    pos3 = make_position(side="LONG", entry_z=-3.0)
    if not engine3._check_micro_z_reversal(pos3, profile):
        ok(f"LONG abs(ΔZ) < {threshold} → no invalidation")
    else:
        fail("LONG Micro-Z should NOT trigger (within threshold)")

    # SHORT: No reversal when within threshold
    ctx4 = MockContextRegistry(z=3.0 - 0.5)  # ΔZ = -0.5, abs=0.5 < threshold
    croupier4 = MockCroupier(context_registry=ctx4)
    engine4 = slim_engine(croupier4)
    pos4 = make_position(side="SHORT", entry_z=3.0)
    if not engine4._check_micro_z_reversal(pos4, profile):
        ok("abs(ΔZ) within threshold → no invalidation")
    else:
        fail("Small abs(ΔZ) should not invalidate")


async def test_scale_out():
    print("\n" + "=" * 60)
    print(" PILLAR 1: SCALE OUT")
    print("=" * 60)

    profile = blue_chip_profile()
    at_atr = profile["scale_out"]["at_atr"]
    croupier = MockCroupier()
    engine = slim_engine(croupier)
    pos = make_position(side="LONG", entry_price=100.0, entry_atr=2.0)

    target_price = 100.0 + 2.0 * at_atr
    hit = await engine._check_scale_out(pos, target_price, profile)
    if hit and pos.scaled_out:
        ok(f"Scale-out at {at_atr}×ATR marks scaled_out=True")
    else:
        fail("Scale-out should trigger at ATR distance")

    await asyncio.sleep(0.05)
    if len(croupier.scale_out_calls) == 1:
        tid, fraction, reason = croupier.scale_out_calls[0]
        if tid == pos.trade_id and fraction == profile["scale_out"]["fraction"] and reason == "SO_TARGET_REACHED":
            ok("Scale-out schedules scale_out_structural with correct fraction")
        else:
            fail(f"Unexpected scale_out call: {croupier.scale_out_calls}")
    else:
        fail("Scale-out should enqueue scale_out_structural")

    # Already scaled — on_tick skips pillar (guard is in on_tick, not _check_scale_out)
    croupier2 = MockCroupier()
    pos2 = make_position(
        scaled_out=True,
        entry_atr=2.0,
        timestamp=time.time() - 30.0,
        trade_id="so_repeat",
    )
    croupier2.position_tracker.open_positions = [pos2]
    engine2 = slim_engine(croupier2)
    tick = TickEvent(type=None, timestamp=time.time(), symbol="BTCUSDT", price=target_price)
    await engine2.on_tick(tick)
    await asyncio.sleep(0.05)
    if len(croupier2.scale_out_calls) == 0:
        ok("scaled_out=True → on_tick skips scale-out pillar")
    else:
        fail("Should not scale out twice when scaled_out=True")

    pos3 = make_position(entry_atr=0.0)
    if not await engine._check_scale_out(pos3, target_price, profile):
        ok("entry_atr=0 → scale-out skipped")
    else:
        fail("Zero ATR should skip scale-out")


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
    if len(croupier.close_calls) == 0 and len(croupier.scale_out_calls) == 0:
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
    print(" SLIM EXIT ENGINE VALIDATOR (Layer 0.E)")
    print(" Tests each pillar's math independently")
    print("=" * 60)

    test_profile_resolution()
    await test_micro_z_reversal()
    await test_scale_out()
    await test_on_tick_grace_and_pending()

    print("\n" + "=" * 60)
    print(" ✅ ALL SLIM EXIT ENGINE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
