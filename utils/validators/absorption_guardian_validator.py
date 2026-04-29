#!/usr/bin/env python3
"""
Layer 0.B: Guardian Math Validator
------------------------------------
Validates that the 3 guardian methods in AbsorptionDetector
compute correct metrics and make correct pass/fail decisions.

Tests (isolated, no bot, no FootprintRegistry, no SensorManager):
  1. _calculate_z_score()  — correct z-score math with known history
  2. _calculate_concentration() — correct time-based ratio
  3. _calculate_noise()    — correct opposite-volume ratio
  4. _validate_magnitude() — passes/fails at threshold boundary
  5. _validate_velocity()  — passes/fails at threshold boundary
  6. _validate_noise()     — passes/fails at threshold boundary
  7. Guardian chain: all-pass → signal, any-fail → None

Input  → synthetic metrics (known values)
Output → assert exact float results and boolean decisions

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
    """Build a minimal FootprintData with a single level for testing."""
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
    print("  LAYER 0.B: GUARDIAN MATH VALIDATOR")
    print("  Absorption V1 — Isolated component test")
    print("=" * 60)

    detector = AbsorptionDetector()
    symbol = "TEST/USDT"
    base_ts = 1000.0

    # ─────────────────────────────────────────────────────────
    # TEST 1: _calculate_z_score() — known history
    # ─────────────────────────────────────────────────────────
    section("TEST 1: _calculate_z_score() with known history")

    # Seed history: 10 deltas all = 10.0 → mean=10, std=0 → z=0
    detector.delta_history[symbol] = [(base_ts - i, 10.0) for i in range(10, 0, -1)]

    # Add a new delta = 10.0 (same as mean) → z should be 0
    z = detector._calculate_z_score(symbol, 10.0, base_ts)
    if not math.isclose(z, 0.0, abs_tol=1e-6):
        fail(f"z_score for delta=mean should be 0.0, got {z}")
    ok(f"z_score(delta=mean) = {z:.4f} (expected 0.0)")

    # Seed history with variance: [10]*9 + [20] → mean≈10.9, std≈2.8
    # Then add delta=20 → z should be positive and > 1
    detector.delta_history[symbol] = [(base_ts - i, 10.0) for i in range(10, 1, -1)]
    detector.delta_history[symbol].append((base_ts - 1, 20.0))

    z_high = detector._calculate_z_score(symbol, 20.0, base_ts + 1)
    if z_high <= 1.0:
        fail(f"z_score for outlier delta should be > 1.0, got {z_high:.4f}")
    ok(f"z_score(outlier delta) = {z_high:.4f} (expected > 1.0)")

    # Insufficient history (< 10 points) → z = 0.0
    detector.delta_history["NEW_SYM"] = [(base_ts, 100.0)]  # only 1 point
    z_insuf = detector._calculate_z_score("NEW_SYM", 100.0, base_ts + 1)
    if not math.isclose(z_insuf, 0.0, abs_tol=1e-6):
        fail(f"z_score with < 10 history should be 0.0, got {z_insuf}")
    ok(f"z_score(insufficient history) = {z_insuf:.4f} (expected 0.0)")

    # ─────────────────────────────────────────────────────────
    # TEST 2: _calculate_concentration() — time-based ratio
    # ─────────────────────────────────────────────────────────
    section("TEST 2: _calculate_concentration() — time-based heuristic")

    current_ts = 2000.0

    # Level updated 10s ago → high concentration (< 30s)
    fp_recent = build_footprint_with_level(78.50, 100.0, 50.0, last_update=current_ts - 10)
    conc_recent = detector._calculate_concentration(fp_recent, 78.50, current_ts)
    if conc_recent < 0.8:
        fail(f"Recent level (10s ago) should have concentration >= 0.8, got {conc_recent:.2f}")
    ok(f"concentration(10s ago) = {conc_recent:.2f} (expected >= 0.8)")

    # Level updated 45s ago → medium concentration (30-60s)
    fp_medium = build_footprint_with_level(78.50, 100.0, 50.0, last_update=current_ts - 45)
    conc_medium = detector._calculate_concentration(fp_medium, 78.50, current_ts)
    if not (0.4 <= conc_medium <= 0.8):
        fail(f"Medium-age level (45s ago) should have concentration in [0.4, 0.8], got {conc_medium:.2f}")
    ok(f"concentration(45s ago) = {conc_medium:.2f} (expected in [0.4, 0.8])")

    # Level updated 120s ago → low concentration (> 60s)
    fp_old = build_footprint_with_level(78.50, 100.0, 50.0, last_update=current_ts - 120)
    conc_old = detector._calculate_concentration(fp_old, 78.50, current_ts)
    if conc_old >= 0.5:
        fail(f"Old level (120s ago) should have concentration < 0.5, got {conc_old:.2f}")
    ok(f"concentration(120s ago) = {conc_old:.2f} (expected < 0.5)")

    # Non-existent level → 0.0
    fp_empty = FootprintData(tick_size=0.01)
    conc_none = detector._calculate_concentration(fp_empty, 78.50, current_ts)
    if not math.isclose(conc_none, 0.0):
        fail(f"Missing level should return concentration=0.0, got {conc_none}")
    ok(f"concentration(missing level) = {conc_none:.2f} (expected 0.0)")

    # ─────────────────────────────────────────────────────────
    # TEST 3: _calculate_noise() — opposite volume ratio
    # ─────────────────────────────────────────────────────────
    section("TEST 3: _calculate_noise() — opposite volume ratio")

    # SELL_EXHAUSTION (delta < 0): noise = ask_vol / total
    # ask=10, bid=90, delta=-80 → noise = 10/100 = 0.10 (clean sell absorption)
    noise_clean_sell = detector._calculate_noise(ask_vol=10.0, bid_vol=90.0, delta=-80.0)
    if not math.isclose(noise_clean_sell, 0.10, rel_tol=1e-5):
        fail(f"Clean sell absorption noise={noise_clean_sell:.4f}, expected 0.10")
    ok(f"noise(clean sell absorption) = {noise_clean_sell:.4f} (expected 0.10)")

    # SELL_EXHAUSTION noisy: ask=50, bid=50, delta=-0 → noise = 50/100 = 0.50
    noise_noisy_sell = detector._calculate_noise(ask_vol=50.0, bid_vol=50.0, delta=-1.0)
    if not math.isclose(noise_noisy_sell, 0.50, rel_tol=1e-5):
        fail(f"Noisy sell noise={noise_noisy_sell:.4f}, expected 0.50")
    ok(f"noise(noisy sell) = {noise_noisy_sell:.4f} (expected 0.50)")

    # BUY_EXHAUSTION (delta > 0): noise = bid_vol / total
    # ask=90, bid=10, delta=+80 → noise = 10/100 = 0.10 (clean buy absorption)
    noise_clean_buy = detector._calculate_noise(ask_vol=90.0, bid_vol=10.0, delta=80.0)
    if not math.isclose(noise_clean_buy, 0.10, rel_tol=1e-5):
        fail(f"Clean buy absorption noise={noise_clean_buy:.4f}, expected 0.10")
    ok(f"noise(clean buy absorption) = {noise_clean_buy:.4f} (expected 0.10)")

    # Zero volume → max noise (1.0)
    noise_zero = detector._calculate_noise(ask_vol=0.0, bid_vol=0.0, delta=1.0)
    if not math.isclose(noise_zero, 1.0):
        fail(f"Zero volume noise={noise_zero:.4f}, expected 1.0")
    ok(f"noise(zero volume) = {noise_zero:.4f} (expected 1.0)")

    # ─────────────────────────────────────────────────────────
    # TEST 4: _validate_magnitude() — threshold boundary
    # ─────────────────────────────────────────────────────────
    section("TEST 4: _validate_magnitude() — threshold boundary")

    threshold = detector.z_score_min
    print(f"  Current z_score_min = {threshold}")

    # Exactly at threshold → PASS
    if not detector._validate_magnitude(threshold):
        fail(f"z={threshold} (exactly at threshold) should PASS")
    ok(f"z={threshold} (at threshold) → PASS")

    # Just above → PASS
    if not detector._validate_magnitude(threshold + 0.01):
        fail(f"z={threshold + 0.01} (above threshold) should PASS")
    ok(f"z={threshold + 0.01} (above threshold) → PASS")

    # Just below → FAIL
    if detector._validate_magnitude(threshold - 0.01):
        fail(f"z={threshold - 0.01} (below threshold) should FAIL")
    ok(f"z={threshold - 0.01} (below threshold) → FAIL")

    # Negative z (absolute value check)
    if not detector._validate_magnitude(-threshold):
        fail(f"z={-threshold} (negative, abs at threshold) should PASS")
    ok(f"z={-threshold} (negative abs at threshold) → PASS")

    if detector._validate_magnitude(-(threshold - 0.01)):
        fail(f"z={-(threshold - 0.01)} (negative, abs below threshold) should FAIL")
    ok(f"z={-(threshold - 0.01)} (negative abs below threshold) → FAIL")

    # ─────────────────────────────────────────────────────────
    # TEST 5: _validate_velocity() — threshold boundary
    # ─────────────────────────────────────────────────────────
    section("TEST 5: _validate_velocity() — threshold boundary")

    threshold_v = detector.concentration_min
    print(f"  Current concentration_min = {threshold_v}")

    if not detector._validate_velocity(threshold_v):
        fail(f"conc={threshold_v} (at threshold) should PASS")
    ok(f"conc={threshold_v} (at threshold) → PASS")

    if not detector._validate_velocity(threshold_v + 0.01):
        fail(f"conc={threshold_v + 0.01} (above threshold) should PASS")
    ok(f"conc={threshold_v + 0.01} (above threshold) → PASS")

    if detector._validate_velocity(threshold_v - 0.01):
        fail(f"conc={threshold_v - 0.01} (below threshold) should FAIL")
    ok(f"conc={threshold_v - 0.01} (below threshold) → FAIL")

    # ─────────────────────────────────────────────────────────
    # TEST 6: _validate_noise() — threshold boundary
    # ─────────────────────────────────────────────────────────
    section("TEST 6: _validate_noise() — threshold boundary")

    threshold_n = detector.noise_max
    print(f"  Current noise_max = {threshold_n}")

    if not detector._validate_noise(threshold_n):
        fail(f"noise={threshold_n} (at threshold) should PASS")
    ok(f"noise={threshold_n} (at threshold) → PASS")

    if not detector._validate_noise(threshold_n - 0.01):
        fail(f"noise={threshold_n - 0.01} (below threshold) should PASS")
    ok(f"noise={threshold_n - 0.01} (below threshold) → PASS")

    if detector._validate_noise(threshold_n + 0.01):
        fail(f"noise={threshold_n + 0.01} (above threshold) should FAIL")
    ok(f"noise={threshold_n + 0.01} (above threshold) → FAIL")

    # ─────────────────────────────────────────────────────────
    # TEST 7: Guardian chain — all-pass vs any-fail
    # ─────────────────────────────────────────────────────────
    section("TEST 7: Guardian chain — all-pass vs any-fail")

    # All pass
    all_pass = (
        detector._validate_magnitude(detector.z_score_min + 1.0)
        and detector._validate_velocity(detector.concentration_min + 0.1)
        and detector._validate_noise(detector.noise_max - 0.1)
    )
    if not all_pass:
        fail("All-pass guardian chain should return True")
    ok("All guardians pass → chain = True")

    # Magnitude fails
    mag_fail = (
        detector._validate_magnitude(0.0)
        and detector._validate_velocity(detector.concentration_min + 0.1)
        and detector._validate_noise(detector.noise_max - 0.1)
    )
    if mag_fail:
        fail("Magnitude-fail chain should return False")
    ok("Magnitude fails → chain = False")

    # Velocity fails
    vel_fail = (
        detector._validate_magnitude(detector.z_score_min + 1.0)
        and detector._validate_velocity(0.0)
        and detector._validate_noise(detector.noise_max - 0.1)
    )
    if vel_fail:
        fail("Velocity-fail chain should return False")
    ok("Velocity fails → chain = False")

    # Noise fails
    noise_fail = (
        detector._validate_magnitude(detector.z_score_min + 1.0)
        and detector._validate_velocity(detector.concentration_min + 0.1)
        and detector._validate_noise(1.0)
    )
    if noise_fail:
        fail("Noise-fail chain should return False")
    ok("Noise fails → chain = False")

    # ─────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.B PASSED — Guardian math is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
