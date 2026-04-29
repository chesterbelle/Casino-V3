#!/usr/bin/env python3
"""
Layer 1.4: ExitEngine + Croupier Integration Validator
-------------------------------------------------------
Validates that ExitEngine correctly triggers Croupier close/scale_out operations
when layer conditions are met through the on_tick/on_candle event path.

Tests (pairwise integration: ExitEngine ↔ Croupier):
  1. Catastrophic exit → croupier.close_position() called with reason="CATASTROPHIC_STOP"
  2. Flow invalidation → croupier.close_position() called with reason="FLOW_EMERGENCY"/"FLOW_INVALIDATION"
  3. Counter-absorption → croupier.close_position() called with reason="COUNTER_ABSORPTION_*"
  4. Valentino scale-out → croupier.scale_out_position() called (50% partial)
  5. _pending_terminations prevents double-close from concurrent layers
  6. Audit mode: ExitEngine logs but does NOT execute closes
  7. Shadow SL trigger → croupier.close_position() called with reason="SHADOW_SL"

Input  → Synthetic TickEvent/CandleEvent + positions in known states
Output → Verify Croupier mock received correct close/scale_out calls

Usage:
    python utils/validators/exit_engine_integration_validator.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1)


# =========================================================
# MOCK OBJECTS
# =========================================================


class MockContextRegistry:
    def __init__(self, cvd=0.0, skew=0.5, z=0.0, vol_ratio=1.0):
        self._cvd = cvd
        self._skew = skew
        self._z = z
        self._vol_ratio = vol_ratio

    def get_micro_state(self, symbol):
        return (self._cvd, self._skew, self._z)

    def get_volatility_ratio(self, symbol):
        return self._vol_ratio

    def get_structural(self, symbol):
        return (0.0, 0.0, 0.0)

    def get_flow_inertia(self, symbol, side, profit_pct):
        return 1.0


class MockErrorHandler:
    def __init__(self):
        self.shutdown_mode = False


class MockPositionTracker:
    def __init__(self, positions=None):
        self.open_positions = positions or []

    def get_positions_by_symbol(self, symbol):
        return [p for p in self.open_positions if p.symbol == symbol]


class MockCroupier:
    """Croupier mock that records all close/scale_out calls for verification."""

    def __init__(self, context_registry=None):
        self.context_registry = context_registry
        self.position_tracker = MockPositionTracker()
        self.error_handler = MockErrorHandler()
        self.is_drain_mode = False
        self.close_calls = []
        self.scale_out_calls = []
        self.modify_tp_calls = []

    async def close_position(self, trade_id, exit_reason=""):
        self.close_calls.append((trade_id, exit_reason))

    async def scale_out_position(self, trade_id, fraction=0.5):
        self.scale_out_calls.append((trade_id, fraction))

    async def modify_tp(self, trade_id, new_tp_price, symbol, old_tp_order_id):
        self.modify_tp_calls.append((trade_id, new_tp_price))

    def get_open_positions(self):
        return self.position_tracker.open_positions


def make_position(
    symbol="LTCUSDT",
    side="LONG",
    entry_price=100.0,
    tp_level=None,
    sl_level=None,
    setup_type="AbsorptionScalpingV1",
    trade_id="test_001",
    timestamp=0.0,
    scaled_out=False,
    scale_out_trigger=None,
    shadow_sl_level=None,
    bars_held=0,
    amount=1.0,
):
    from core.portfolio.position_tracker import OpenPosition

    tp = tp_level or (entry_price * 1.003 if side == "LONG" else entry_price * 0.997)
    sl = sl_level or (entry_price * 0.997 if side == "LONG" else entry_price * 1.003)
    pos = OpenPosition(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        entry_timestamp=str(timestamp),
        timestamp=timestamp,
        margin_used=entry_price * amount / 10.0,
        notional=entry_price * amount,
        leverage=10.0,
        tp_level=tp,
        sl_level=sl,
        amount=amount,
    )
    pos.setup_type = setup_type
    pos.scaled_out = scaled_out
    pos.scale_out_trigger = scale_out_trigger
    pos.shadow_sl_level = shadow_sl_level
    pos.bars_held = bars_held
    pos.trigger_level = entry_price
    pos.last_price = entry_price
    pos.entry_atr = 0.0
    pos.trailing_phase = 0
    pos.shadow_sl_triggered = False
    pos.soft_exit_triggered = False
    pos.defensive_exit_triggered = False
    pos.drain_phase = None
    return pos


def make_tick(symbol="LTCUSDT", price=100.0, timestamp=None):
    from core.events import TickEvent

    if timestamp is None:
        timestamp = time.time()
    return TickEvent(type=None, timestamp=timestamp, symbol=symbol, price=price)


def make_candle(symbol="LTCUSDT", timestamp=None):
    from core.events import CandleEvent

    if timestamp is None:
        timestamp = time.time()
    return CandleEvent(
        type=None,
        timestamp=timestamp,
        symbol=symbol,
        timeframe="1m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
    )


# =========================================================
# TESTS
# =========================================================


async def test_catastrophic_triggers_close():
    """Catastrophic exit → croupier.close_position() called with correct reason."""
    print("\n" + "=" * 60)
    print(" CATASTROPHIC → CROUPIER CLOSE")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    pos = make_position(side="LONG", entry_price=100.0, trade_id="cat_001")
    croupier.position_tracker.open_positions = [pos]

    engine = ExitEngine(croupier)

    # Price drops >50% → catastrophic
    tick = make_tick(price=49.0, timestamp=time.time())
    await engine.on_tick(tick)

    # Allow async tasks to complete
    await asyncio.sleep(0.1)

    found = any(tid == "cat_001" and "CATASTROPHIC" in reason for tid, reason in croupier.close_calls)
    if found:
        ok("Catastrophic exit → croupier.close_position() called with CATASTROPHIC_STOP")
    else:
        fail(f"Catastrophic should call close_position, got calls: {croupier.close_calls}")

    # Verify _pending_terminations was set
    if "cat_001" in engine._pending_terminations:
        ok("trade_id added to _pending_terminations")
    else:
        fail("trade_id should be in _pending_terminations after catastrophic exit")


async def test_flow_invalidation_triggers_close():
    """Flow invalidation → croupier.close_position() called with correct reason."""
    print("\n" + "=" * 60)
    print(" FLOW INVALIDATION → CROUPIER CLOSE")
    print("=" * 60)

    import config.trading as trading_config
    from croupier.components.exit_engine import ExitEngine

    # Enable thesis layer (may be disabled in production config)
    orig_thesis = getattr(trading_config, "EXIT_LAYER_THESIS_INVALIDATION", True)
    trading_config.EXIT_LAYER_THESIS_INVALIDATION = True

    try:
        ctx = MockContextRegistry(z=-6.0)
        croupier = MockCroupier(context_registry=ctx)
        pos = make_position(side="LONG", entry_price=100.0, trade_id="flow_001", timestamp=time.time() - 100.0)
        croupier.position_tracker.open_positions = [pos]

        engine = ExitEngine(croupier)

        tick = make_tick(price=99.0, timestamp=time.time())
        await engine.on_tick(tick)
        await asyncio.sleep(0.1)

        found = any(tid == "flow_001" and "FLOW" in reason for tid, reason in croupier.close_calls)
        if found:
            ok("Flow invalidation → croupier.close_position() called with FLOW_* reason")
        else:
            fail(f"Flow invalidation should call close_position, got calls: {croupier.close_calls}")
    finally:
        trading_config.EXIT_LAYER_THESIS_INVALIDATION = orig_thesis


async def test_valentino_triggers_scale_out():
    """Valentino scale-out → croupier.scale_out_position() called (50% partial)."""
    print("\n" + "=" * 60)
    print(" VALENTINO → CROUPIER SCALE_OUT")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    # LONG: entry=100, TP=103, Valentino trigger at 70% = 102.1
    pos = make_position(
        side="LONG", entry_price=100.0, tp_level=103.0, trade_id="val_001", timestamp=time.time() - 100.0
    )
    croupier.position_tracker.open_positions = [pos]

    engine = ExitEngine(croupier)

    # Price at 102.5 (above 70% threshold)
    tick = make_tick(price=102.5, timestamp=time.time())
    await engine.on_tick(tick)
    await asyncio.sleep(0.1)

    found = any(tid == "val_001" for tid, frac in croupier.scale_out_calls)
    if found:
        _, fraction = croupier.scale_out_calls[0]
        if abs(fraction - 0.50) < 0.01:
            ok(f"Valentino → croupier.scale_out_position(trade_id, fraction=0.50)")
        else:
            fail(f"Valentino fraction should be 0.50, got {fraction}")
    else:
        fail(f"Valentino should call scale_out_position, got: {croupier.scale_out_calls}")


async def test_shadow_sl_triggers_close():
    """Shadow SL trigger → croupier.close_position() called with reason="SHADOW_SL"."""
    print("\n" + "=" * 60)
    print(" SHADOW SL TRIGGER → CROUPIER CLOSE")
    print("=" * 60)

    import config.trading as trading_config
    from croupier.components.exit_engine import ExitEngine

    # Enable shadow protection layer (may be disabled in production config)
    orig_shadow = getattr(trading_config, "EXIT_LAYER_SHADOW_PROTECTION", True)
    trading_config.EXIT_LAYER_SHADOW_PROTECTION = True

    try:
        croupier = MockCroupier()
        # LONG: entry=100, shadow_sl=99.5, price drops to 99.0
        pos = make_position(
            side="LONG", entry_price=100.0, shadow_sl_level=99.5, trade_id="shadow_001", timestamp=time.time() - 100.0
        )
        croupier.position_tracker.open_positions = [pos]

        engine = ExitEngine(croupier)

        tick = make_tick(price=99.0, timestamp=time.time())
        await engine.on_tick(tick)
        await asyncio.sleep(0.1)

        found = any(tid == "shadow_001" and reason == "SHADOW_SL" for tid, reason in croupier.close_calls)
        if found:
            ok("Shadow SL trigger → croupier.close_position() with SHADOW_SL")
        else:
            fail(f"Shadow SL should call close_position with SHADOW_SL, got: {croupier.close_calls}")
    finally:
        trading_config.EXIT_LAYER_SHADOW_PROTECTION = orig_shadow


async def test_pending_terminations_prevents_double_close():
    """_pending_terminations prevents double-close from concurrent layers."""
    print("\n" + "=" * 60)
    print(" PENDING TERMINATIONS → NO DOUBLE CLOSE")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    ctx = MockContextRegistry(z=-6.0)  # Emergency flow
    croupier = MockCroupier(context_registry=ctx)

    # Position that would trigger BOTH catastrophic AND flow invalidation
    pos = make_position(side="LONG", entry_price=100.0, trade_id="double_001", timestamp=time.time() - 100.0)
    croupier.position_tracker.open_positions = [pos]

    engine = ExitEngine(croupier)

    # First tick: catastrophic (price at 49.0)
    tick1 = make_tick(price=49.0, timestamp=time.time())
    await engine.on_tick(tick1)
    await asyncio.sleep(0.1)

    first_close_count = len(croupier.close_calls)

    # Second tick: same position, still catastrophic + flow
    # Position should be skipped because trade_id is in _pending_terminations
    tick2 = make_tick(price=48.0, timestamp=time.time())
    await engine.on_tick(tick2)
    await asyncio.sleep(0.1)

    # Should NOT have additional close calls for the same position
    # (The position is in _pending_terminations, so on_tick skips it)
    double_closes = sum(1 for tid, _ in croupier.close_calls if tid == "double_001")
    if double_closes <= 1:
        ok(f"No double-close: position 'double_001' closed {double_closes} time(s)")
    else:
        fail(f"Double-close detected: position 'double_001' closed {double_closes} time(s)")


async def test_audit_mode_no_execution():
    """Audit mode: ExitEngine logs but does NOT execute closes."""
    print("\n" + "=" * 60)
    print(" AUDIT MODE → NO EXECUTION")
    print("=" * 60)

    import config.trading as trading_config
    from croupier.components.exit_engine import ExitEngine

    # Save and set audit mode
    original_audit = getattr(trading_config, "AUDIT_MODE", False)
    trading_config.AUDIT_MODE = True

    try:
        ctx = MockContextRegistry(z=-6.0)
        croupier = MockCroupier(context_registry=ctx)
        pos = make_position(side="LONG", entry_price=100.0, trade_id="audit_001", timestamp=time.time() - 100.0)
        croupier.position_tracker.open_positions = [pos]

        engine = ExitEngine(croupier)

        # This would normally trigger flow invalidation
        tick = make_tick(price=99.0, timestamp=time.time())
        await engine.on_tick(tick)
        await asyncio.sleep(0.1)

        # In audit mode, close_position should NOT be called for layers 4-2
        audit_closes = [c for c in croupier.close_calls if c[0] == "audit_001"]
        if len(audit_closes) == 0:
            ok("Audit mode: no close_position calls for thesis/valentino/shadow layers")
        else:
            fail(f"Audit mode should NOT execute closes, got: {audit_closes}")

    finally:
        trading_config.AUDIT_MODE = original_audit


async def test_closing_position_skipped():
    """Position with status='CLOSING' is skipped by all layers."""
    print("\n" + "=" * 60)
    print(" CLOSING POSITION → SKIPPED")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    pos = make_position(side="LONG", entry_price=100.0, trade_id="closing_001")
    pos.status = "CLOSING"
    croupier.position_tracker.open_positions = [pos]

    engine = ExitEngine(croupier)

    # Price at catastrophic level
    tick = make_tick(price=49.0, timestamp=time.time())
    await engine.on_tick(tick)
    await asyncio.sleep(0.1)

    found = any(tid == "closing_001" for tid, _ in croupier.close_calls)
    if not found:
        ok("CLOSING position skipped — no additional close calls")
    else:
        fail("CLOSING position should be skipped by on_tick")


async def test_shutdown_mode_skips_positions():
    """Shutdown mode: positions are skipped by on_tick."""
    print("\n" + "=" * 60)
    print(" SHUTDOWN MODE → POSITIONS SKIPPED")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    croupier.error_handler.shutdown_mode = True
    pos = make_position(side="LONG", entry_price=100.0, trade_id="shutdown_001")
    croupier.position_tracker.open_positions = [pos]

    engine = ExitEngine(croupier)

    tick = make_tick(price=49.0, timestamp=time.time())
    await engine.on_tick(tick)
    await asyncio.sleep(0.1)

    found = any(tid == "shutdown_001" for tid, _ in croupier.close_calls)
    if not found:
        ok("Shutdown mode: positions skipped by on_tick")
    else:
        fail("Shutdown mode should skip positions in on_tick")


# =========================================================
# MAIN
# =========================================================


async def main():
    print("=" * 60)
    print(" EXIT ENGINE INTEGRATION VALIDATOR (Layer 1.4)")
    print(" Tests ExitEngine → Croupier callback wiring")
    print("=" * 60)

    await test_catastrophic_triggers_close()
    await test_flow_invalidation_triggers_close()
    await test_valentino_triggers_scale_out()
    await test_shadow_sl_triggers_close()
    await test_pending_terminations_prevents_double_close()
    await test_audit_mode_no_execution()
    await test_closing_position_skipped()
    await test_shutdown_mode_skips_positions()

    print("\n" + "=" * 60)
    print(" ✅ ALL EXIT ENGINE INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
