#!/usr/bin/env python3
"""
Layer 1.4: SlimExitEngine + Croupier Integration Validator
----------------------------------------------------------
Validates SlimExitEngine triggers the correct Croupier callbacks via on_tick.

Tests (SlimExitEngine ↔ Croupier):
  1. Micro-Z Reversal → close_position(MZ_REVERSAL, prefer_maker=True)
  2. Scale-out → scale_out_structural(SO_TARGET_REACHED)
  3. Pillar priority: Micro-Z reversal blocks Scale-out on same tick
  4. Non-OPEN positions skipped
  5. Patience lock grace period blocks early tactical exits

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
    timestamp=None,
    entry_atr=1.0,
    entry_z=None,
    scaled_out=False,
    be_activated=False,
    shadow_sl_level=None,
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
    pos.entry_atr = entry_atr
    pos.scaled_out = scaled_out
    pos.be_activated = be_activated
    pos.shadow_sl_level = shadow_sl_level
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

    profile = trading_config.ASSET_EXIT_PROFILES["BLUE_CHIP"]
    threshold = profile["micro_z_reversal"]["threshold"]
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


async def test_scale_out_triggers_structural():
    print("\n" + "=" * 60)
    print(" SCALE OUT → scale_out_structural")
    print("=" * 60)

    profile = trading_config.ASSET_EXIT_PROFILES["BLUE_CHIP"]
    at_atr = profile["scale_out"]["at_atr"]
    fraction = profile["scale_out"]["fraction"]
    entry_atr = 2.0
    target_price = 100.0 + entry_atr * at_atr

    croupier = MockCroupier()
    pos = make_position(
        entry_price=100.0,
        entry_atr=entry_atr,
        trade_id="so_001",
        timestamp=past_grace_timestamp(),
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=target_price)
    await engine.on_tick(tick)
    await asyncio.sleep(0.15)

    found = any(
        tid == "so_001" and frac == fraction and reason == "SO_TARGET_REACHED"
        for tid, frac, reason in croupier.scale_out_calls
    )
    if found:
        ok(f"Scale-out → scale_out_structural({fraction:.0%}, SO_TARGET_REACHED)")
    else:
        fail(f"Expected scale-out call, got: {croupier.scale_out_calls}")


async def test_pillar_priority_single_tick():
    print("\n" + "=" * 60)
    print(" PILLAR PRIORITY → ONE ACTION PER TICK")
    print("=" * 60)

    profile = trading_config.ASSET_EXIT_PROFILES["BLUE_CHIP"]
    threshold = profile["micro_z_reversal"]["threshold"]
    at_atr = profile["scale_out"]["at_atr"]
    entry_z = -3.0
    entry_atr = 2.0
    # abs(ΔZ) > threshold → MZ fires, SO skipped
    z = entry_z + threshold + 1.0
    ctx = MockContextRegistry(z=z)

    croupier = MockCroupier(context_registry=ctx)
    scale_out_price = 100.0 + entry_atr * at_atr
    pos = make_position(
        side="LONG",
        entry_z=entry_z,
        entry_atr=entry_atr,
        entry_price=100.0,
        trade_id="prio_001",
        timestamp=past_grace_timestamp(),
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    await engine.on_tick(make_tick(price=scale_out_price))
    await asyncio.sleep(0.15)

    closes = [c for c in croupier.close_calls if c[0] == "prio_001"]
    scale_outs = [s for s in croupier.scale_out_calls if s[0] == "prio_001"]
    if len(closes) == 1 and closes[0][1] == "MZ_REVERSAL" and len(scale_outs) == 0:
        ok("Micro-Z reversal fires; scale-out skipped on same tick (pillar priority)")
    else:
        fail(f"Expected 1 MZ close (MZ_REVERSAL) and 0 scale-outs, got closes={closes}, scale_outs={scale_outs}")


async def test_non_open_position_skipped():
    print("\n" + "=" * 60)
    print(" NON-OPEN POSITION → SKIPPED")
    print("=" * 60)

    croupier = MockCroupier(context_registry=MockContextRegistry(z=0.0))
    pos = make_position(
        side="LONG",
        entry_z=-3.0,
        trade_id="closed_001",
        timestamp=past_grace_timestamp(),
        status="CLOSING",
    )
    croupier.position_tracker.open_positions = [pos]
    engine = slim_engine(croupier)

    tick = make_tick(price=100.0)
    await engine.on_tick(tick)
    await asyncio.sleep(0.1)

    if not croupier.close_calls and not croupier.scale_out_calls:
        ok("status != OPEN → no Croupier exit callbacks")
    else:
        fail(f"CLOSING position should be skipped, got closes={croupier.close_calls}")


async def test_patience_lock_blocks_early_exit():
    print("\n" + "=" * 60)
    print(" PATIENCE LOCK → NO EARLY TACTICAL EXIT")
    print("=" * 60)

    croupier = MockCroupier(context_registry=MockContextRegistry(z=0.0))
    pos = make_position(
        side="LONG",
        entry_z=-3.0,
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
    print(" SLIM EXIT ENGINE INTEGRATION VALIDATOR (Layer 1.4)")
    print(" Tests SlimExitEngine → Croupier callback wiring")
    print("=" * 60)

    await test_micro_z_reversal_triggers_close()
    await test_scale_out_triggers_structural()
    await test_pillar_priority_single_tick()
    await test_non_open_position_skipped()
    await test_patience_lock_blocks_early_exit()

    print("\n" + "=" * 60)
    print(" ✅ ALL SLIM EXIT ENGINE INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
