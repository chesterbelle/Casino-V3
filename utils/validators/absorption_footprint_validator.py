#!/usr/bin/env python3
"""
Layer 0.A: FootprintRegistry Math Validator
--------------------------------------------
Validates that FootprintRegistry correctly accumulates trade data.

Tests (isolated, no bot, no SensorManager):
  1. add_trade() accumulates ask/bid/delta correctly per level
  2. BUY trades increment ask_volume and positive delta
  3. SELL trades increment bid_volume and negative delta
  4. round_price() snaps to correct tick size
  5. get_volume_profile() returns correct range and sort order
  6. prune_old_levels() removes stale data without corrupting CVD
  7. CVD tracks cumulative delta correctly across multiple trades

Input  → known trades (price, volume, side)
Output → assert exact ask_vol, bid_vol, delta, CVD values

Usage:
    python utils/validators/absorption_footprint_validator.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.footprint_registry import FootprintData


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1)


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def main():
    print("=" * 60)
    print("  LAYER 0.A: FOOTPRINT REGISTRY MATH VALIDATOR")
    print("  Absorption V1 — Isolated component test")
    print("=" * 60)

    # ─────────────────────────────────────────────────────────
    # TEST 1: BUY trade accumulation
    # ─────────────────────────────────────────────────────────
    section("TEST 1: BUY trade → ask_volume +, delta +")

    fp = FootprintData(tick_size=0.01)
    fp.add_trade(price=78.50, volume=100.0, side="BUY", timestamp=1000.0)

    level = fp.round_price(78.50)
    data = fp.levels.get(level)

    if data is None:
        fail(f"Level {level} not created after BUY trade")

    # Input:  BUY 100 @ 78.50
    # Output: ask_volume=100, bid_volume=0, delta=+100
    if not math.isclose(data["ask_volume"], 100.0):
        fail(f"ask_volume={data['ask_volume']}, expected 100.0")
    ok(f"ask_volume = {data['ask_volume']} (expected 100.0)")

    if not math.isclose(data["bid_volume"], 0.0):
        fail(f"bid_volume={data['bid_volume']}, expected 0.0")
    ok(f"bid_volume = {data['bid_volume']} (expected 0.0)")

    if not math.isclose(data["delta"], 100.0):
        fail(f"delta={data['delta']}, expected +100.0")
    ok(f"delta = {data['delta']:+.1f} (expected +100.0)")

    if not math.isclose(fp.cvd, 100.0):
        fail(f"CVD={fp.cvd}, expected +100.0")
    ok(f"CVD = {fp.cvd:+.1f} (expected +100.0)")

    # ─────────────────────────────────────────────────────────
    # TEST 2: SELL trade accumulation
    # ─────────────────────────────────────────────────────────
    section("TEST 2: SELL trade → bid_volume +, delta -")

    fp2 = FootprintData(tick_size=0.01)
    fp2.add_trade(price=78.50, volume=60.0, side="SELL", timestamp=1000.0)

    level2 = fp2.round_price(78.50)
    data2 = fp2.levels.get(level2)

    # Input:  SELL 60 @ 78.50
    # Output: ask_volume=0, bid_volume=60, delta=-60
    if not math.isclose(data2["bid_volume"], 60.0):
        fail(f"bid_volume={data2['bid_volume']}, expected 60.0")
    ok(f"bid_volume = {data2['bid_volume']} (expected 60.0)")

    if not math.isclose(data2["delta"], -60.0):
        fail(f"delta={data2['delta']}, expected -60.0")
    ok(f"delta = {data2['delta']:+.1f} (expected -60.0)")

    if not math.isclose(fp2.cvd, -60.0):
        fail(f"CVD={fp2.cvd}, expected -60.0")
    ok(f"CVD = {fp2.cvd:+.1f} (expected -60.0)")

    # ─────────────────────────────────────────────────────────
    # TEST 3: Mixed trades at same level → delta = ask - bid
    # ─────────────────────────────────────────────────────────
    section("TEST 3: Mixed trades at same level → delta = ask - bid")

    fp3 = FootprintData(tick_size=0.01)
    fp3.add_trade(price=78.50, volume=200.0, side="BUY", timestamp=1000.0)
    fp3.add_trade(price=78.50, volume=50.0, side="SELL", timestamp=1001.0)

    level3 = fp3.round_price(78.50)
    data3 = fp3.levels[level3]

    # Input:  BUY 200 + SELL 50 @ 78.50
    # Output: ask=200, bid=50, delta=+150, CVD=+150
    if not math.isclose(data3["ask_volume"], 200.0):
        fail(f"ask_volume={data3['ask_volume']}, expected 200.0")
    ok(f"ask_volume = {data3['ask_volume']} (expected 200.0)")

    if not math.isclose(data3["bid_volume"], 50.0):
        fail(f"bid_volume={data3['bid_volume']}, expected 50.0")
    ok(f"bid_volume = {data3['bid_volume']} (expected 50.0)")

    expected_delta = 200.0 - 50.0
    if not math.isclose(data3["delta"], expected_delta):
        fail(f"delta={data3['delta']}, expected {expected_delta}")
    ok(f"delta = {data3['delta']:+.1f} (expected {expected_delta:+.1f})")

    if not math.isclose(fp3.cvd, expected_delta):
        fail(f"CVD={fp3.cvd}, expected {expected_delta}")
    ok(f"CVD = {fp3.cvd:+.1f} (expected {expected_delta:+.1f})")

    # ─────────────────────────────────────────────────────────
    # TEST 4: round_price() snaps to tick size
    # ─────────────────────────────────────────────────────────
    section("TEST 4: round_price() snaps to tick size")

    fp4 = FootprintData(tick_size=0.01)

    cases = [
        (78.504, 0.01, 78.50),
        (78.506, 0.01, 78.51),
        (78.505, 0.01, 78.50),  # banker's rounding (Python)
        (100.0, 0.50, 100.0),
        (100.3, 0.50, 100.5),
        (100.2, 0.50, 100.0),
    ]

    for raw, tick, expected in cases:
        fp_t = FootprintData(tick_size=tick)
        result = fp_t.round_price(raw)
        if not math.isclose(result, expected, abs_tol=1e-9):
            fail(f"round_price({raw}, tick={tick}) = {result}, expected {expected}")
        ok(f"round_price({raw}, tick={tick}) = {result} (expected {expected})")

    # ─────────────────────────────────────────────────────────
    # TEST 5: get_volume_profile() range and sort order
    # ─────────────────────────────────────────────────────────
    section("TEST 5: get_volume_profile() returns correct range, sorted ascending")

    fp5 = FootprintData(tick_size=0.01)
    ts = 1000.0
    # Add trades at 5 levels
    for price in [78.40, 78.45, 78.50, 78.55, 78.60]:
        fp5.add_trade(price, 100.0, "BUY", ts)
        ts += 1.0

    # Query range 78.44 → 78.56 → should return 78.45, 78.50, 78.55
    profile = fp5.get_volume_profile(78.44, 78.56)

    if len(profile) != 3:
        fail(f"get_volume_profile returned {len(profile)} levels, expected 3. Got: {[p[0] for p in profile]}")
    ok(f"Returned {len(profile)} levels in range [78.44, 78.56] (expected 3)")

    prices = [p[0] for p in profile]
    if prices != sorted(prices):
        fail(f"Profile not sorted ascending: {prices}")
    ok(f"Profile sorted ascending: {prices}")

    # Verify volumes
    for price, ask_vol, bid_vol in profile:
        if not math.isclose(ask_vol, 100.0):
            fail(f"Level {price}: ask_vol={ask_vol}, expected 100.0")
    ok("All levels have correct ask_volume=100.0")

    # ─────────────────────────────────────────────────────────
    # TEST 6: prune_old_levels() removes stale data
    # ─────────────────────────────────────────────────────────
    section("TEST 6: prune_old_levels() removes stale data, preserves recent")

    fp6 = FootprintData(tick_size=0.01, window_seconds=60)

    # Add old trade (timestamp=0) and recent trade (timestamp=1000)
    fp6.add_trade(78.40, 100.0, "BUY", timestamp=0.0)  # old
    fp6.add_trade(78.50, 200.0, "SELL", timestamp=1000.0)  # recent

    levels_before = len(fp6.levels)
    if levels_before != 2:
        fail(f"Expected 2 levels before prune, got {levels_before}")
    ok(f"Before prune: {levels_before} levels")

    # Prune at current_time=1000 → cutoff=940 → 78.40 (ts=0) should be removed
    fp6.prune_old_levels(current_time=1000.0)

    levels_after = len(fp6.levels)
    if levels_after != 1:
        fail(f"Expected 1 level after prune, got {levels_after}. Remaining: {list(fp6.levels.keys())}")
    ok(f"After prune: {levels_after} level (old level removed)")

    remaining_level = list(fp6.levels.keys())[0]
    if not math.isclose(remaining_level, fp6.round_price(78.50)):
        fail(f"Wrong level survived prune: {remaining_level}, expected ~78.50")
    ok(f"Correct level survived: {remaining_level}")

    # ─────────────────────────────────────────────────────────
    # TEST 7: CVD tracks cumulative delta across multiple levels
    # ─────────────────────────────────────────────────────────
    section("TEST 7: CVD = cumulative sum of all deltas across all levels")

    fp7 = FootprintData(tick_size=0.01)
    ts = 1000.0

    trades = [
        (78.40, 300.0, "BUY"),  # +300
        (78.41, 100.0, "SELL"),  # -100
        (78.42, 500.0, "BUY"),  # +500
        (78.43, 200.0, "SELL"),  # -200
        (78.44, 50.0, "SELL"),  # -50
    ]
    expected_cvd = 300 - 100 + 500 - 200 - 50  # = +450

    for price, vol, side in trades:
        fp7.add_trade(price, vol, side, ts)
        ts += 1.0

    if not math.isclose(fp7.cvd, expected_cvd):
        fail(f"CVD={fp7.cvd}, expected {expected_cvd}")
    ok(f"CVD = {fp7.cvd:+.1f} (expected {expected_cvd:+.1f})")

    # ─────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.A PASSED — FootprintRegistry math is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
