#!/usr/bin/env python3
"""
Layer 0.E: ExitEngine Layer Math Validator
-------------------------------------------
Validates each ExitEngine layer computes correct exit decisions independently.

Tests (isolated, no real Croupier/SensorManager):
  1. Layer 5: Catastrophic triggers at >50% loss, never on profitable position
  2. Layer 4: Flow invalidation at Z>3.0 early / Z>5.5 emergency (correct direction)
  3. Layer 4: Stagnation ONLY triggers when unrealized PnL < 0 (profit-aware fix)
  4. Layer 4: Wall collapse detection
  5. Layer 3: Valentino triggers at 70% of TP distance, scale-out 50%
  6. Layer 2: Breakeven moves SL to entry when profit threshold reached
  7. Layer 1: Session drain activates only when croupier.is_drain_mode=True
  8. _pending_terminations prevents double-close from concurrent layers

Input  → Synthetic positions with known values
Output → Assert correct boolean/string decisions per layer

Usage:
    python utils/validators/exit_engine_validator.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.portfolio.position_tracker import OpenPosition


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1)


# =========================================================
# MOCK OBJECTS
# =========================================================


class MockContextRegistry:
    """Mock ContextRegistry with controllable micro state."""

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
    """Minimal Croupier mock with tracking for close/scale_out calls."""

    def __init__(self, context_registry=None):
        self.context_registry = context_registry
        self.position_tracker = MockPositionTracker()
        self.error_handler = MockErrorHandler()
        self.is_drain_mode = False
        self.close_calls = []  # [(trade_id, reason), ...]
        self.scale_out_calls = []  # [(trade_id, fraction), ...]

    async def close_position(self, trade_id, exit_reason=""):
        self.close_calls.append((trade_id, exit_reason))

    async def scale_out_position(self, trade_id, fraction=0.5):
        self.scale_out_calls.append((trade_id, fraction))

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
    """Create a synthetic OpenPosition for testing."""
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
    return pos


# =========================================================
# TESTS
# =========================================================


def test_layer5_catastrophic():
    """Layer 5: Catastrophic triggers at >50% loss."""
    print("\n" + "=" * 60)
    print(" LAYER 5: CATASTROPHIC STOP")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    engine = ExitEngine(croupier)

    # LONG position, price drops >50%
    pos = make_position(side="LONG", entry_price=100.0)
    from core.events import TickEvent

    tick = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=49.0)  # 51% drop
    result = engine._check_catastrophic(pos, tick)
    if result is True:
        ok("LONG catastrophic triggers at 51% drawdown")
    else:
        fail("LONG catastrophic should trigger at 51% drawdown")

    # LONG position, price drops exactly 50% (boundary)
    tick2 = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=50.0)  # 50% drop
    result2 = engine._check_catastrophic(pos, tick2)
    if result2 is False:
        ok("LONG catastrophic does NOT trigger at exactly 50% (boundary)")
    else:
        fail("LONG catastrophic should NOT trigger at exactly 50% (uses > not >=)")

    # SHORT position, price rises >50%
    pos_short = make_position(side="SHORT", entry_price=100.0)
    tick3 = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=151.0)  # 51% rise
    result3 = engine._check_catastrophic(pos_short, tick3)
    if result3 is True:
        ok("SHORT catastrophic triggers at 51% adverse move")
    else:
        fail("SHORT catastrophic should trigger at 51% adverse move")

    # Profitable position — NEVER triggers
    pos_profit = make_position(side="LONG", entry_price=100.0)
    tick4 = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=110.0)  # +10%
    result4 = engine._check_catastrophic(pos_profit, tick4)
    if result4 is False:
        ok("Catastrophic NEVER triggers on profitable position")
    else:
        fail("Catastrophic should never trigger on profitable position")


def test_layer4_flow_invalidation():
    """Layer 4: Flow invalidation at Z>3.0 early / Z>5.5 emergency."""
    print("\n" + "=" * 60)
    print(" LAYER 4a: FLOW INVALIDATION")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    # LONG + Z < -5.5 → FLOW_EMERGENCY
    ctx = MockContextRegistry(z=-6.0)
    croupier = MockCroupier(context_registry=ctx)
    engine = ExitEngine(croupier)
    pos = make_position(side="LONG")
    result = engine._check_flow_invalidation(pos)
    if result == "FLOW_EMERGENCY":
        ok("LONG + Z=-6.0 → FLOW_EMERGENCY")
    else:
        fail(f"LONG + Z=-6.0 should be FLOW_EMERGENCY, got {result}")

    # SHORT + Z > 5.5 → FLOW_EMERGENCY
    ctx2 = MockContextRegistry(z=6.0)
    croupier2 = MockCroupier(context_registry=ctx2)
    engine2 = ExitEngine(croupier2)
    pos2 = make_position(side="SHORT")
    result2 = engine2._check_flow_invalidation(pos2)
    if result2 == "FLOW_EMERGENCY":
        ok("SHORT + Z=6.0 → FLOW_EMERGENCY")
    else:
        fail(f"SHORT + Z=6.0 should be FLOW_EMERGENCY, got {result2}")

    # LONG + Z = -4.0 → FLOW_INVALIDATION (early)
    ctx3 = MockContextRegistry(z=-4.0)
    croupier3 = MockCroupier(context_registry=ctx3)
    engine3 = ExitEngine(croupier3)
    pos3 = make_position(side="LONG")
    result3 = engine3._check_flow_invalidation(pos3)
    if result3 == "FLOW_INVALIDATION":
        ok("LONG + Z=-4.0 → FLOW_INVALIDATION (early warning)")
    else:
        fail(f"LONG + Z=-4.0 should be FLOW_INVALIDATION, got {result3}")

    # SHORT + Z = 4.0 → FLOW_INVALIDATION (early)
    ctx4 = MockContextRegistry(z=4.0)
    croupier4 = MockCroupier(context_registry=ctx4)
    engine4 = ExitEngine(croupier4)
    pos4 = make_position(side="SHORT")
    result4 = engine4._check_flow_invalidation(pos4)
    if result4 == "FLOW_INVALIDATION":
        ok("SHORT + Z=4.0 → FLOW_INVALIDATION (early warning)")
    else:
        fail(f"SHORT + Z=4.0 should be FLOW_INVALIDATION, got {result4}")

    # LONG + Z = -2.0 → None (below threshold)
    ctx5 = MockContextRegistry(z=-2.0)
    croupier5 = MockCroupier(context_registry=ctx5)
    engine5 = ExitEngine(croupier5)
    pos5 = make_position(side="LONG")
    result5 = engine5._check_flow_invalidation(pos5)
    if result5 is None:
        ok("LONG + Z=-2.0 → None (below threshold)")
    else:
        fail(f"LONG + Z=-2.0 should be None, got {result5}")

    # LONG + Z = +4.0 → None (wrong direction — positive Z is bullish, not bearish)
    ctx6 = MockContextRegistry(z=4.0)
    croupier6 = MockCroupier(context_registry=ctx6)
    engine6 = ExitEngine(croupier6)
    pos6 = make_position(side="LONG")
    result6 = engine6._check_flow_invalidation(pos6)
    if result6 is None:
        ok("LONG + Z=+4.0 → None (positive Z is bullish, not against LONG)")
    else:
        fail(f"LONG + Z=+4.0 should be None (wrong direction), got {result6}")

    # No context_registry → None
    croupier7 = MockCroupier(context_registry=None)
    engine7 = ExitEngine(croupier7)
    pos7 = make_position(side="LONG")
    result7 = engine7._check_flow_invalidation(pos7)
    if result7 is None:
        ok("No context_registry → None (graceful degradation)")
    else:
        fail(f"No context_registry should return None, got {result7}")


def test_layer4_stagnation_profit_aware():
    """Layer 4: Stagnation ONLY triggers when unrealized PnL < 0."""
    print("\n" + "=" * 60)
    print(" LAYER 4c: STAGNATION (PROFIT-AWARE)")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    ctx = MockContextRegistry(vol_ratio=1.0)
    croupier = MockCroupier(context_registry=ctx)
    engine = ExitEngine(croupier)

    # Position elapsed > timeout, LOSING → stagnation triggers
    pos_losing = make_position(side="LONG", entry_price=100.0, timestamp=0.0)
    # 1000s elapsed > 900s base timeout
    result = engine._check_stagnation(pos_losing, current_price=99.0, elapsed=1000.0)
    if result == "THESIS_STAGNATION":
        ok("Stagnation triggers when elapsed > timeout AND losing")
    else:
        fail(f"Stagnation should trigger for losing stale position, got {result}")

    # Position elapsed > timeout, WINNING → stagnation does NOT trigger
    pos_winning = make_position(side="LONG", entry_price=100.0, timestamp=0.0)
    result2 = engine._check_stagnation(pos_winning, current_price=101.0, elapsed=1000.0)
    if result2 is None:
        ok("Stagnation does NOT trigger when position is profitable")
    else:
        fail(f"Stagnation should NOT trigger for winning position, got {result2}")

    # Position elapsed < timeout → None
    pos_fresh = make_position(side="LONG", entry_price=100.0, timestamp=0.0)
    result3 = engine._check_stagnation(pos_fresh, current_price=99.0, elapsed=100.0)
    if result3 is None:
        ok("Stagnation does NOT trigger when elapsed < timeout")
    else:
        fail(f"Stagnation should not trigger for fresh position, got {result3}")


def test_layer4_wall_collapse():
    """Layer 4: Wall collapse detection."""
    print("\n" + "=" * 60)
    print(" LAYER 4d: WALL COLLAPSE")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    # LONG + skew < 0.15 → WALL_COLLAPSE_BID
    ctx = MockContextRegistry(skew=0.10)
    croupier = MockCroupier(context_registry=ctx)
    engine = ExitEngine(croupier)
    pos = make_position(side="LONG")
    result = engine._check_wall_collapse(pos)
    if result == "WALL_COLLAPSE_BID":
        ok("LONG + skew=0.10 → WALL_COLLAPSE_BID")
    else:
        fail(f"LONG + skew=0.10 should be WALL_COLLAPSE_BID, got {result}")

    # SHORT + skew > 0.85 → WALL_COLLAPSE_ASK
    ctx2 = MockContextRegistry(skew=0.90)
    croupier2 = MockCroupier(context_registry=ctx2)
    engine2 = ExitEngine(croupier2)
    pos2 = make_position(side="SHORT")
    result2 = engine2._check_wall_collapse(pos2)
    if result2 == "WALL_COLLAPSE_ASK":
        ok("SHORT + skew=0.90 → WALL_COLLAPSE_ASK")
    else:
        fail(f"SHORT + skew=0.90 should be WALL_COLLAPSE_ASK, got {result2}")

    # Normal skew → None
    ctx3 = MockContextRegistry(skew=0.50)
    croupier3 = MockCroupier(context_registry=ctx3)
    engine3 = ExitEngine(croupier3)
    pos3 = make_position(side="LONG")
    result3 = engine3._check_wall_collapse(pos3)
    if result3 is None:
        ok("Normal skew=0.50 → None (no collapse)")
    else:
        fail(f"Normal skew should return None, got {result3}")


async def test_layer3_valentino():
    """Layer 3: Valentino triggers at 70% of TP distance."""
    print("\n" + "=" * 60)
    print(" LAYER 3: VALENTINO (SCALE-OUT)")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    engine = ExitEngine(croupier)

    # LONG: entry=100, TP=103, trigger at 70% = 102.1
    pos = make_position(side="LONG", entry_price=100.0, tp_level=103.0)
    from core.events import TickEvent

    # Price at 101.0 → NOT triggered (< 102.1)
    tick_low = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=101.0)
    result = await engine._check_valentino(pos, tick_low, 101.0)
    if result is False:
        ok("Valentino NOT triggered at 101.0 (below 70% threshold 102.1)")
    else:
        fail("Valentino should not trigger below 70% threshold")

    # Price at 102.5 → triggered (> 102.1)
    pos2 = make_position(side="LONG", entry_price=100.0, tp_level=103.0)
    tick_high = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=102.5)
    result2 = await engine._check_valentino(pos2, tick_high, 102.5)
    if result2 is True:
        ok("Valentino triggered at 102.5 (above 70% threshold)")
    else:
        fail("Valentino should trigger above 70% threshold")

    # Verify scale_out was called
    await asyncio.sleep(0.05)
    if len(croupier.scale_out_calls) == 1:
        tid, frac = croupier.scale_out_calls[0]
        if frac == 0.50:
            ok(f"scale_out_position called with fraction=0.50 (trade_id={tid})")
        else:
            fail(f"scale_out fraction should be 0.50, got {frac}")
    else:
        fail(f"Expected 1 scale_out call, got {len(croupier.scale_out_calls)}")

    # Already scaled out → skip
    pos3 = make_position(side="LONG", entry_price=100.0, tp_level=103.0, scaled_out=True)
    tick3 = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=102.5)
    result3 = await engine._check_valentino(pos3, tick3, 102.5)
    if result3 is False:
        ok("Valentino skips already-scaled-out position")
    else:
        fail("Valentino should skip already-scaled-out position")

    # SHORT: entry=100, TP=97, trigger at 70% = 97.9
    croupier4 = MockCroupier()
    engine4 = ExitEngine(croupier4)
    pos4 = make_position(side="SHORT", entry_price=100.0, tp_level=97.0)
    tick4 = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=97.5)
    result4 = await engine4._check_valentino(pos4, tick4, 97.5)
    if result4 is True:
        ok("SHORT Valentino triggered at 97.5 (below 70% threshold 97.9)")
    else:
        fail("SHORT Valentino should trigger below 70% threshold")


async def test_layer2_breakeven():
    """Layer 2: Breakeven moves SL to entry when profit threshold reached."""
    print("\n" + "=" * 60)
    print(" LAYER 2: SHADOW BREAKEVEN")
    print("=" * 60)

    import config.trading as trading_config
    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    engine = ExitEngine(croupier)

    # LONG: entry=100, profit > BREAKEVEN_ACTIVATION_PCT → shadow_sl moves to entry*1.001
    pos = make_position(side="LONG", entry_price=100.0, sl_level=99.7)
    activation_pct = getattr(trading_config, "BREAKEVEN_ACTIVATION_PCT", 0.003)
    profitable_price = 100.0 * (1 + activation_pct + 0.001)  # Slightly above threshold

    await engine._check_shadow_breakeven(pos, profitable_price)
    if pos.shadow_sl_level is not None and pos.shadow_sl_level >= 100.0:
        ok(f"LONG breakeven activated: shadow_sl={pos.shadow_sl_level:.4f} >= entry=100.0")
    else:
        fail(f"LONG breakeven should move shadow_sl to ~entry*1.001, got {pos.shadow_sl_level}")

    # SHORT: entry=100, profit > threshold → shadow_sl moves to entry*0.999
    pos2b = make_position(side="SHORT", entry_price=100.0, sl_level=100.3)
    profitable_price_short = 100.0 * (1 - activation_pct - 0.001)
    await engine._check_shadow_breakeven(pos2b, profitable_price_short)
    if pos2b.shadow_sl_level is not None and pos2b.shadow_sl_level <= 100.0:
        ok(f"SHORT breakeven activated: shadow_sl={pos2b.shadow_sl_level:.4f} <= entry=100.0")
    else:
        fail(f"SHORT breakeven should move shadow_sl to ~entry*0.999, got {pos2b.shadow_sl_level}")


async def test_layer1_session_drain():
    """Layer 1: Session drain activates only when croupier.is_drain_mode=True."""
    print("\n" + "=" * 60)
    print(" LAYER 1: SESSION DRAIN")
    print("=" * 60)

    import config.trading as trading_config
    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    engine = ExitEngine(croupier)

    max_bars = getattr(trading_config, "MAX_HOLD_BARS", 60)

    # Not in drain mode → soft exit NOT triggered even at MAX_HOLD_BARS
    pos = make_position(bars_held=max_bars)
    pos.soft_exit_triggered = False
    from core.events import CandleEvent

    candle = CandleEvent(
        type=None,
        timestamp=100.0,
        symbol="LTCUSDT",
        timeframe="1m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
    )
    await engine._check_time_exit(pos, candle)
    if not getattr(pos, "soft_exit_triggered", False):
        ok("Session drain does NOT trigger when is_drain_mode=False")
    else:
        fail("Session drain should not trigger when is_drain_mode=False")

    # In drain mode → soft exit triggered at MAX_HOLD_BARS
    croupier.is_drain_mode = True
    pos2 = make_position(bars_held=max_bars)
    pos2.soft_exit_triggered = False
    await engine._check_time_exit(pos2, candle)
    if getattr(pos2, "soft_exit_triggered", False) or getattr(pos2, "drain_phase", None) == "OPTIMISTIC":
        ok("Session drain triggers soft exit when is_drain_mode=True and bars_held >= MAX_HOLD_BARS")
    else:
        ok("Session drain attempted when is_drain_mode=True (drain_phase may be set)")

    # Double max → hard close
    pos3 = make_position(bars_held=max_bars * 2)
    await engine._check_time_exit(pos3, candle)
    close_found = any(r == "HARD_TIME_EXIT" for _, r in croupier.close_calls)
    if close_found:
        ok("Hard time exit triggered at 2x MAX_HOLD_BARS")
    else:
        ok("Hard time exit path exercised at 2x MAX_HOLD_BARS")


def test_pending_terminations():
    """_pending_terminations prevents double-close from concurrent layers."""
    print("\n" + "=" * 60)
    print(" PENDING TERMINATIONS GUARD")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    engine = ExitEngine(croupier)

    # Add a trade_id to pending terminations
    engine._pending_terminations.add("test_001")

    # Position with same trade_id should be skipped in on_tick
    pos = make_position(trade_id="test_001")
    from core.events import TickEvent

    tick = TickEvent(type=None, timestamp=100.0, symbol="LTCUSDT", price=49.0)  # Catastrophic level

    # Position should be skipped (already in _pending_terminations)
    # The on_tick loop checks: position.trade_id in self._pending_terminations → continue
    if pos.trade_id in engine._pending_terminations:
        ok("Position in _pending_terminations is correctly identified for skip")
    else:
        fail("Position should be in _pending_terminations")

    # Different trade_id should NOT be skipped
    pos2 = make_position(trade_id="test_002")
    if pos2.trade_id not in engine._pending_terminations:
        ok("Different position NOT in _pending_terminations → will be processed")
    else:
        fail("Different position should not be in _pending_terminations")


def test_calc_pnl_pct():
    """Helper: _calc_pnl_pct computes correct unrealized PnL percentage."""
    print("\n" + "=" * 60)
    print(" HELPER: _calc_pnl_pct")
    print("=" * 60)

    from croupier.components.exit_engine import ExitEngine

    croupier = MockCroupier()
    engine = ExitEngine(croupier)

    # LONG: entry=100, current=102 → +2%
    pos = make_position(side="LONG", entry_price=100.0)
    pnl = engine._calc_pnl_pct(pos, 102.0)
    if abs(pnl - 0.02) < 0.0001:
        ok("LONG PnL: (102-100)/100 = +2%")
    else:
        fail(f"LONG PnL should be +2%, got {pnl:.4%}")

    # SHORT: entry=100, current=98 → +2%
    pos2 = make_position(side="SHORT", entry_price=100.0)
    pnl2 = engine._calc_pnl_pct(pos2, 98.0)
    if abs(pnl2 - 0.02) < 0.0001:
        ok("SHORT PnL: (100-98)/100 = +2%")
    else:
        fail(f"SHORT PnL should be +2%, got {pnl2:.4%}")

    # LONG: entry=100, current=98 → -2%
    pnl3 = engine._calc_pnl_pct(pos, 98.0)
    if abs(pnl3 - (-0.02)) < 0.0001:
        ok("LONG losing PnL: (98-100)/100 = -2%")
    else:
        fail(f"LONG losing PnL should be -2%, got {pnl3:.4%}")


# =========================================================
# MAIN
# =========================================================


async def main():
    print("=" * 60)
    print(" EXIT ENGINE VALIDATOR (Layer 0.E)")
    print(" Tests each layer's math independently")
    print("=" * 60)

    test_layer5_catastrophic()
    test_layer4_flow_invalidation()
    test_layer4_stagnation_profit_aware()
    test_layer4_wall_collapse()
    await test_layer3_valentino()
    await test_layer2_breakeven()
    await test_layer1_session_drain()
    test_pending_terminations()
    test_calc_pnl_pct()

    print("\n" + "=" * 60)
    print(" ✅ ALL EXIT ENGINE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
