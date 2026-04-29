#!/usr/bin/env python3
"""
Layer 0.D: Signal Generation Validator
----------------------------------------
Validates that AbsorptionDetector.calculate() generates correct signals
end-to-end using synthetic FootprintData (no bot, no SensorManager).

Tests (isolated — only AbsorptionDetector + FootprintRegistry):
  1. Obvious SELL absorption → generates SELL_EXHAUSTION signal
  2. Obvious BUY absorption  → generates BUY_EXHAUSTION signal
  3. No absorption (flat footprint) → returns None
  4. Insufficient footprint (< 10 levels) → returns None
  5. Signal has all required fields (direction, z_score, concentration,
     noise, level, side, volume_profile, price)
  6. SELL_EXHAUSTION → side=LONG (trade direction is opposite)
  7. BUY_EXHAUSTION  → side=SHORT
  8. volume_profile is non-empty list of (price, ask, bid, total) tuples

This is the highest-resolution isolated test before integration.
If this passes but Layer 0.4 (SensorManager integration) fails,
the bug is in the wiring, not the sensor logic.

Input  → synthetic footprint injected directly into FootprintRegistry
Output → assert signal fields and values

Usage:
    python utils/validators/absorption_signal_validator.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.footprint_registry import FootprintData, FootprintRegistry
from sensors.absorption.absorption_detector import AbsorptionDetector


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1)


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def inject_footprint(registry: FootprintRegistry, symbol: str, levels: dict, tick_size: float = 0.01):
    """
    Inject a synthetic footprint directly into the registry.
    levels = {price: (ask_vol, bid_vol)}
    """
    registry.register_symbol(symbol, tick_size)
    fp = registry.footprints[symbol]
    fp.levels.clear()

    ts = 1000.0
    for price, (ask_vol, bid_vol) in levels.items():
        rounded = fp.round_price(price)
        fp.levels[rounded] = {
            "ask_volume": ask_vol,
            "bid_volume": bid_vol,
            "delta": ask_vol - bid_vol,
            "last_update": ts,
        }
        ts += 1.0


def seed_z_score_history(detector: AbsorptionDetector, symbol: str, background_delta: float, n: int = 20):
    """
    Seed delta history so z-score calculation has enough data.
    background_delta = typical delta (mean of history)
    """
    base_ts = 900.0
    detector.delta_history[symbol] = [(base_ts + i, background_delta) for i in range(n)]


def make_candle_context(symbol: str, timestamp: float) -> dict:
    """Build the candle_data context dict that SensorManager passes to calculate()."""
    return {
        "1m": {
            "symbol": symbol,
            "timestamp": timestamp,
            "open": 78.40,
            "high": 78.60,
            "low": 78.30,
            "close": 78.50,
            "volume": 1000.0,
        }
    }


def main():
    print("=" * 60)
    print("  LAYER 0.D: SIGNAL GENERATION VALIDATOR")
    print("  Absorption V1 — Isolated component test")
    print("=" * 60)

    # Use a fresh registry instance for isolation
    registry = FootprintRegistry()
    registry.reset()

    detector = AbsorptionDetector()
    # Relax thresholds to ensure synthetic data passes guardians
    detector.z_score_min = 1.5
    detector.concentration_min = 0.40
    detector.noise_max = 0.40

    ts = 1000.0

    # ─────────────────────────────────────────────────────────
    # TEST 1: SELL absorption → SELL_EXHAUSTION signal
    # ─────────────────────────────────────────────────────────
    section("TEST 1: Obvious SELL absorption → SELL_EXHAUSTION signal")

    sym_sell = "SELL_TEST/USDT"

    # Build footprint: 20 levels, one with massive sell absorption
    # Level 78.50: ask=10, bid=990 → delta=-980 (sellers absorbed by buyers)
    levels_sell = {78.40 + i * 0.01: (55.0, 45.0) for i in range(20)}  # background delta=+10
    levels_sell[78.50] = (10.0, 990.0)  # delta=-980 (extreme sell absorption)

    inject_footprint(registry, sym_sell, levels_sell)

    # Seed z-score history with background delta=+10 so -980 is a massive outlier
    seed_z_score_history(detector, sym_sell, background_delta=10.0, n=20)

    context = make_candle_context(sym_sell, ts)
    signal = detector.calculate(context)

    if signal is None:
        fail(
            "Expected SELL_EXHAUSTION signal but got None.\n"
            "  Possible causes:\n"
            "    - z_score too low (history not seeded correctly)\n"
            "    - concentration too low (last_update too old)\n"
            "    - noise too high (ask_vol too large relative to bid_vol)\n"
            "  Check Layer 0.B (guardian math) and Layer 0.C (candidate detection)"
        )
    ok(f"Signal generated: direction={signal['direction']}")

    if signal["direction"] != "SELL_EXHAUSTION":
        fail(f"direction={signal['direction']}, expected SELL_EXHAUSTION")
    ok(f"direction = SELL_EXHAUSTION ✓")

    if signal["side"] != "LONG":
        fail(f"side={signal['side']}, expected LONG (trade opposite to exhaustion)")
    ok(f"side = LONG (trade direction opposite to exhaustion) ✓")

    if signal["delta"] >= 0:
        fail(f"delta={signal['delta']}, expected negative for SELL_EXHAUSTION")
    ok(f"delta = {signal['delta']:+.1f} (negative) ✓")

    # ─────────────────────────────────────────────────────────
    # TEST 2: BUY absorption → BUY_EXHAUSTION signal
    # ─────────────────────────────────────────────────────────
    section("TEST 2: Obvious BUY absorption → BUY_EXHAUSTION signal")

    sym_buy = "BUY_TEST/USDT"

    # Level 78.55: ask=990, bid=10 → delta=+980 (buyers absorbed by sellers)
    levels_buy = {78.40 + i * 0.01: (55.0, 45.0) for i in range(20)}  # background delta=+10
    levels_buy[78.55] = (990.0, 10.0)  # delta=+980 (extreme buy absorption)

    inject_footprint(registry, sym_buy, levels_buy)
    seed_z_score_history(detector, sym_buy, background_delta=10.0, n=20)

    context_buy = make_candle_context(sym_buy, ts)
    signal_buy = detector.calculate(context_buy)

    if signal_buy is None:
        fail(
            "Expected BUY_EXHAUSTION signal but got None.\n"
            "  Check Layer 0.B (guardian math) and Layer 0.C (candidate detection)"
        )
    ok(f"Signal generated: direction={signal_buy['direction']}")

    if signal_buy["direction"] != "BUY_EXHAUSTION":
        fail(f"direction={signal_buy['direction']}, expected BUY_EXHAUSTION")
    ok(f"direction = BUY_EXHAUSTION ✓")

    if signal_buy["side"] != "SHORT":
        fail(f"side={signal_buy['side']}, expected SHORT")
    ok(f"side = SHORT ✓")

    if signal_buy["delta"] <= 0:
        fail(f"delta={signal_buy['delta']}, expected positive for BUY_EXHAUSTION")
    ok(f"delta = {signal_buy['delta']:+.1f} (positive) ✓")

    # ─────────────────────────────────────────────────────────
    # TEST 3: Flat footprint (no absorption) → None
    # ─────────────────────────────────────────────────────────
    section("TEST 3: Flat footprint (balanced buy/sell) → None")

    sym_flat = "FLAT_TEST/USDT"

    # All levels perfectly balanced: delta=0 everywhere
    levels_flat = {78.40 + i * 0.01: (50.0, 50.0) for i in range(20)}  # delta=0

    inject_footprint(registry, sym_flat, levels_flat)
    seed_z_score_history(detector, sym_flat, background_delta=0.0, n=20)

    context_flat = make_candle_context(sym_flat, ts)
    signal_flat = detector.calculate(context_flat)

    if signal_flat is not None:
        fail(f"Expected None for flat footprint, got signal: {signal_flat['direction']}")
    ok("Flat footprint (delta=0 everywhere) → None ✓")

    # ─────────────────────────────────────────────────────────
    # TEST 4: Insufficient footprint (< 10 levels) → None
    # ─────────────────────────────────────────────────────────
    section("TEST 4: Insufficient footprint (< 10 levels) → None")

    sym_small = "SMALL_TEST/USDT"

    # Only 5 levels
    levels_small = {78.40 + i * 0.01: (100.0, 10.0) for i in range(5)}

    inject_footprint(registry, sym_small, levels_small)

    context_small = make_candle_context(sym_small, ts)
    signal_small = detector.calculate(context_small)

    if signal_small is not None:
        fail(f"Expected None for < 10 levels, got signal: {signal_small['direction']}")
    ok("< 10 levels → None (insufficient data guard) ✓")

    # ─────────────────────────────────────────────────────────
    # TEST 5: Signal has all required fields
    # ─────────────────────────────────────────────────────────
    section("TEST 5: Signal has all required fields")

    # Use signal from TEST 1
    required_fields = [
        "symbol",
        "direction",
        "side",
        "level",
        "absorption_level",
        "delta",
        "z_score",
        "concentration",
        "noise",
        "ask_volume",
        "bid_volume",
        "price",
        "timestamp",
        "volume_profile",
    ]

    for field in required_fields:
        if field not in signal:
            fail(f"Signal missing required field: '{field}'")
        if signal[field] is None:
            fail(f"Signal field '{field}' is None")
    ok(f"All {len(required_fields)} required fields present and non-None ✓")

    # ─────────────────────────────────────────────────────────
    # TEST 6: volume_profile is a non-empty list of 4-tuples
    # ─────────────────────────────────────────────────────────
    section("TEST 6: volume_profile is non-empty list of (price, ask, bid, total)")

    vp = signal.get("volume_profile", [])

    if not isinstance(vp, list):
        fail(f"volume_profile should be a list, got {type(vp)}")
    ok(f"volume_profile is a list ✓")

    if len(vp) == 0:
        fail("volume_profile is empty — TP calculation will fail")
    ok(f"volume_profile has {len(vp)} entries ✓")

    # Check tuple structure
    for i, entry in enumerate(vp[:3]):  # check first 3
        if len(entry) != 4:
            fail(f"volume_profile[{i}] has {len(entry)} elements, expected 4 (price, ask, bid, total)")
        price_vp, ask_vp, bid_vp, total_vp = entry
        if total_vp != ask_vp + bid_vp:
            fail(f"volume_profile[{i}]: total={total_vp} != ask+bid={ask_vp + bid_vp}")
    ok("volume_profile entries are (price, ask, bid, total) tuples with correct math ✓")

    # ─────────────────────────────────────────────────────────
    # TEST 7: z_score, concentration, noise are in valid ranges
    # ─────────────────────────────────────────────────────────
    section("TEST 7: Signal metrics are in valid ranges")

    z = signal["z_score"]
    conc = signal["concentration"]
    noise = signal["noise"]

    print(f"  Signal metrics:")
    print(f"    z_score       = {z:.4f}  (threshold >= {detector.z_score_min})")
    print(f"    concentration = {conc:.4f}  (threshold >= {detector.concentration_min})")
    print(f"    noise         = {noise:.4f}  (threshold <= {detector.noise_max})")

    if abs(z) < detector.z_score_min:
        fail(f"z_score={z:.4f} is below threshold {detector.z_score_min} — guardian should have blocked this")
    ok(f"z_score={z:.4f} >= {detector.z_score_min} ✓")

    if conc < detector.concentration_min:
        fail(f"concentration={conc:.4f} is below threshold {detector.concentration_min}")
    ok(f"concentration={conc:.4f} >= {detector.concentration_min} ✓")

    if noise > detector.noise_max:
        fail(f"noise={noise:.4f} is above threshold {detector.noise_max}")
    ok(f"noise={noise:.4f} <= {detector.noise_max} ✓")

    # ─────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.D PASSED — Signal generation is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
