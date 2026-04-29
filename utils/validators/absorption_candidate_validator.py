#!/usr/bin/env python3
"""
Layer 0.C: Candidate Detection Validator
------------------------------------------
Validates that _find_extreme_deltas() correctly identifies
absorption candidates from a footprint.

Tests (isolated, no bot, no SensorManager):
  1. Returns top 5% by absolute delta (not by sign)
  2. Returns empty when footprint has < 10 levels with non-zero delta
  3. Returns at least 1 candidate even when top 5% rounds to 0
  4. Returns max 10 candidates regardless of footprint size
  5. Correctly identifies SELL candidates (negative delta)
  6. Correctly identifies BUY candidates (positive delta)
  7. Mixed footprint: top candidate is the one with highest |delta|

Input  → synthetic FootprintData with known delta distribution
Output → assert correct candidates (level, delta, ask_vol, bid_vol)

Usage:
    python utils/validators/absorption_candidate_validator.py
"""

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


def build_footprint(levels: dict, tick_size: float = 0.01) -> FootprintData:
    """
    Build FootprintData from a dict of {price: (ask_vol, bid_vol)}.
    delta = ask_vol - bid_vol is computed automatically.
    """
    fp = FootprintData(tick_size=tick_size)
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
    return fp


def main():
    print("=" * 60)
    print("  LAYER 0.C: CANDIDATE DETECTION VALIDATOR")
    print("  Absorption V1 — Isolated component test")
    print("=" * 60)

    detector = AbsorptionDetector()
    ts = 1000.0

    # ─────────────────────────────────────────────────────────
    # TEST 1: < 10 levels → empty (insufficient data)
    # ─────────────────────────────────────────────────────────
    section("TEST 1: < 10 non-zero delta levels → returns []")

    fp_small = build_footprint(
        {
            78.40: (100, 50),
            78.41: (80, 60),
            78.42: (90, 40),
            # only 3 levels
        }
    )

    candidates = detector._find_extreme_deltas(fp_small)
    if len(candidates) != 0:
        fail(f"Expected 0 candidates with < 10 levels, got {len(candidates)}")
    ok("< 10 levels → returns [] (insufficient data guard works)")

    # ─────────────────────────────────────────────────────────
    # TEST 2: Exactly 10 levels → returns at least 1 candidate
    # ─────────────────────────────────────────────────────────
    section("TEST 2: Exactly 10 levels → returns >= 1 candidate")

    fp_10 = build_footprint({78.40 + i * 0.01: (100.0, 50.0) for i in range(10)})

    candidates_10 = detector._find_extreme_deltas(fp_10)
    if len(candidates_10) < 1:
        fail(f"Expected >= 1 candidate with 10 levels, got {len(candidates_10)}")
    ok(f"10 levels → {len(candidates_10)} candidate(s) (at least 1)")

    # ─────────────────────────────────────────────────────────
    # TEST 3: Top candidate has highest |delta|
    # ─────────────────────────────────────────────────────────
    section("TEST 3: Top candidate = level with highest |delta|")

    # Build 20 levels: most have delta=10, one has delta=-500 (obvious absorption)
    levels_20 = {78.40 + i * 0.01: (55.0, 45.0) for i in range(20)}  # delta=+10 each
    levels_20[78.50] = (10.0, 510.0)  # delta=-500 (strong sell absorption)

    fp_20 = build_footprint(levels_20)
    candidates_20 = detector._find_extreme_deltas(fp_20)

    if len(candidates_20) == 0:
        fail("Expected at least 1 candidate from 20-level footprint")

    top_level, top_delta, top_ask, top_bid = candidates_20[0]
    expected_level = fp_20.round_price(78.50)

    if abs(top_level - expected_level) > 0.001:
        fail(f"Top candidate level={top_level:.2f}, expected {expected_level:.2f} (highest |delta|)")
    ok(f"Top candidate = level {top_level:.2f} with delta={top_delta:+.1f} (highest |delta|)")

    if top_delta >= 0:
        fail(f"Top delta should be negative (sell absorption), got {top_delta:+.1f}")
    ok(f"Top delta is negative ({top_delta:+.1f}) → SELL_EXHAUSTION candidate")

    # ─────────────────────────────────────────────────────────
    # TEST 4: BUY absorption candidate (positive delta)
    # ─────────────────────────────────────────────────────────
    section("TEST 4: BUY absorption candidate (positive delta)")

    levels_buy = {78.40 + i * 0.01: (55.0, 45.0) for i in range(20)}  # delta=+10 each
    levels_buy[78.55] = (600.0, 10.0)  # delta=+590 (strong buy absorption)

    fp_buy = build_footprint(levels_buy)
    candidates_buy = detector._find_extreme_deltas(fp_buy)

    if len(candidates_buy) == 0:
        fail("Expected at least 1 candidate from buy-absorption footprint")

    top_buy_level, top_buy_delta, _, _ = candidates_buy[0]
    expected_buy_level = fp_buy.round_price(78.55)

    if abs(top_buy_level - expected_buy_level) > 0.001:
        fail(f"Top BUY candidate level={top_buy_level:.2f}, expected {expected_buy_level:.2f}")
    ok(f"Top BUY candidate = level {top_buy_level:.2f} with delta={top_buy_delta:+.1f}")

    if top_buy_delta <= 0:
        fail(f"Top BUY delta should be positive, got {top_buy_delta:+.1f}")
    ok(f"Top delta is positive ({top_buy_delta:+.1f}) → BUY_EXHAUSTION candidate")

    # ─────────────────────────────────────────────────────────
    # TEST 5: Max 10 candidates regardless of footprint size
    # ─────────────────────────────────────────────────────────
    section("TEST 5: Max 10 candidates regardless of footprint size (200 levels)")

    # 200 levels with varying deltas
    levels_200 = {}
    for i in range(200):
        ask = 50.0 + i * 2.0  # increasing ask volume
        bid = 50.0
        levels_200[78.00 + i * 0.01] = (ask, bid)

    fp_200 = build_footprint(levels_200)
    candidates_200 = detector._find_extreme_deltas(fp_200)

    if len(candidates_200) > 10:
        fail(f"Expected max 10 candidates, got {len(candidates_200)}")
    ok(f"200-level footprint → {len(candidates_200)} candidates (max 10 cap respected)")

    if len(candidates_200) < 1:
        fail("Expected at least 1 candidate from 200-level footprint")
    ok(f"At least 1 candidate returned")

    # ─────────────────────────────────────────────────────────
    # TEST 6: Zero-delta levels are ignored
    # ─────────────────────────────────────────────────────────
    section("TEST 6: Zero-delta levels are ignored")

    # 15 levels: 5 with delta=0, 10 with delta=10
    levels_zero = {}
    for i in range(5):
        levels_zero[78.40 + i * 0.01] = (50.0, 50.0)  # delta=0
    for i in range(5, 15):
        levels_zero[78.40 + i * 0.01] = (60.0, 40.0)  # delta=+20

    fp_zero = build_footprint(levels_zero)
    candidates_zero = detector._find_extreme_deltas(fp_zero)

    # Only 10 non-zero delta levels → should find candidates
    if len(candidates_zero) == 0:
        fail("Expected candidates from 10 non-zero delta levels")
    ok(f"Zero-delta levels ignored, {len(candidates_zero)} candidate(s) from non-zero levels")

    # Verify no zero-delta candidate slipped through
    for level, delta, ask, bid in candidates_zero:
        if delta == 0.0:
            fail(f"Zero-delta level {level} should not be a candidate")
    ok("No zero-delta levels in candidates")

    # ─────────────────────────────────────────────────────────
    # TEST 7: Candidates sorted by |delta| descending
    # ─────────────────────────────────────────────────────────
    section("TEST 7: Candidates sorted by |delta| descending")

    # 50 levels with clearly different deltas (top 5% = 2-3 candidates)
    levels_sorted = {}
    for i in range(50):
        ask = 100.0 + i * 10.0  # delta increases with i
        levels_sorted[78.00 + i * 0.01] = (ask, 50.0)

    fp_sorted = build_footprint(levels_sorted)
    candidates_sorted = detector._find_extreme_deltas(fp_sorted)

    if len(candidates_sorted) < 2:
        fail(
            f"Expected >= 2 candidates for sort check, got {len(candidates_sorted)} (need 50+ levels for top 5% to yield 2+)"
        )

    # Verify descending order by |delta|
    for i in range(len(candidates_sorted) - 1):
        delta_a = abs(candidates_sorted[i][1])
        delta_b = abs(candidates_sorted[i + 1][1])
        if delta_a < delta_b:
            fail(f"Candidates not sorted: |delta[{i}]|={delta_a} < |delta[{i+1}]|={delta_b}")
    ok(f"{len(candidates_sorted)} candidates sorted by |delta| descending ✓")

    # ─────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.C PASSED — Candidate detection is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
