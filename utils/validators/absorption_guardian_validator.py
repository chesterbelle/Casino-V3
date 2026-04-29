#!/usr/bin/env python3
"""
Layer 0.B: Guardian Math Validator
------------------------------------
Validates that the 4 quality filters in AbsorptionDetector (Phase 1)
compute correct metrics and make correct decisions.

Tests (isolated, no bot, no FootprintRegistry, no SensorManager):
  1. _cross_sectional_zscore() — correct z-score math across footprint
  2. _concentration() — correct time-based ratio
  3. _noise_ratio()    — correct opposite-volume ratio
  4. _check_price_stagnation() — passes/fails based on displacement

Usage:
    python utils/validators/absorption_guardian_validator.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.footprint_registry import FootprintData
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


def build_footprint_with_level(
    level_price: float, ask_vol: float, bid_vol: float, last_update: float, tick_size: float = 0.01
) -> FootprintData:
    fp = FootprintData(tick_size=tick_size)
    rounded = fp.round_price(level_price)
    fp.levels[rounded] = {
        "ask_volume": ask_vol,
        "bid_volume": bid_vol,
        "delta": ask_vol - bid_vol,
        "last_update": last_update,
    }
    return fp


def main():
    print("=" * 60)
    print("  LAYER 0.B: GUARDIAN MATH VALIDATOR (V2)")
    print("=" * 60)

    detector = AbsorptionDetector()

    # ─────────────────────────────────────────────────────────
    # TEST 1: _cross_sectional_zscore()
    # ─────────────────────────────────────────────────────────
    section("TEST 1: _cross_sectional_zscore()")

    # 10 levels with delta=10
    fp_z = FootprintData(tick_size=0.01)
    for i in range(10):
        fp_z.levels[78.00 + i] = {"delta": 10.0}

    # mean=10, std=0 -> z=0
    z_0 = detector._cross_sectional_zscore(fp_z, 10.0)
    if not math.isclose(z_0, 0.0):
        fail(f"Expected z=0 for uniform deltas, got {z_0}")
    ok("z_score(uniform footprint) = 0.0")

    # Add an outlier delta=100
    fp_z.levels[79.00] = {"delta": 100.0}
    z_outlier = detector._cross_sectional_zscore(fp_z, 100.0)
    if z_outlier < 1.0:
        fail(f"Expected z > 1 for outlier, got {z_outlier}")
    ok(f"z_score(outlier delta) = {z_outlier:.2f}")

    # ─────────────────────────────────────────────────────────
    # TEST 2: _concentration()
    # ─────────────────────────────────────────────────────────
    section("TEST 2: _concentration()")

    current_ts = 2000.0
    fp_recent = build_footprint_with_level(78.50, 100.0, 50.0, last_update=current_ts - 10)
    conc_recent = detector._concentration(fp_recent, 78.50, current_ts)
    if conc_recent < 0.8:
        fail(f"Expected conc >= 0.8, got {conc_recent}")
    ok(f"concentration(<30s) = {conc_recent:.2f}")

    fp_old = build_footprint_with_level(78.50, 100.0, 50.0, last_update=current_ts - 120)
    conc_old = detector._concentration(fp_old, 78.50, current_ts)
    if conc_old > 0.4:
        fail(f"Expected conc < 0.4, got {conc_old}")
    ok(f"concentration(>60s) = {conc_old:.2f}")

    # ─────────────────────────────────────────────────────────
    # TEST 3: _noise_ratio()
    # ─────────────────────────────────────────────────────────
    section("TEST 3: _noise_ratio()")

    noise_sell = detector._noise_ratio(ask_vol=10.0, bid_vol=90.0, delta=-80.0)
    if not math.isclose(noise_sell, 0.10):
        fail(f"Expected 0.10, got {noise_sell}")
    ok(f"noise_ratio(clean sell) = {noise_sell:.2f}")

    noise_buy = detector._noise_ratio(ask_vol=90.0, bid_vol=10.0, delta=80.0)
    if not math.isclose(noise_buy, 0.10):
        fail(f"Expected 0.10, got {noise_buy}")
    ok(f"noise_ratio(clean buy) = {noise_buy:.2f}")

    # ─────────────────────────────────────────────────────────
    # TEST 4: _check_price_stagnation()
    # ─────────────────────────────────────────────────────────
    section("TEST 4: _check_price_stagnation()")

    # SELL_EXHAUSTION: open=100, low=99.96 -> dropped 0.04% -> should pass (stagnation=True)
    stag_sell_pass = detector._check_price_stagnation("SYM", "SELL_EXHAUSTION", 99.98, 100.0, 100.0, 99.96)
    if not stag_sell_pass:
        fail("Expected True (stagnation passed) for 0.04% drop")
    ok("stagnation(sell, small drop) = PASS")

    # SELL_EXHAUSTION: open=100, low=99.00 -> dropped 1.0% -> should fail (impulse=False)
    stag_sell_fail = detector._check_price_stagnation("SYM", "SELL_EXHAUSTION", 99.50, 100.0, 100.0, 99.00)
    if stag_sell_fail:
        fail("Expected False (stagnation failed) for 1.0% drop")
    ok("stagnation(sell, big drop) = FAIL (Impulse)")

    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.B PASSED — Guardian math is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
