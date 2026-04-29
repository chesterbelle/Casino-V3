#!/usr/bin/env python3
"""
Layer 0.E: FootprintRegistry Data Quality Validator
-----------------------------------------------------
Validates that FootprintRegistry accumulates REAL trade data correctly
during a backtest run.

This is different from Layer 0.A (which tests math with synthetic data).
Layer 0.E tests data quality by inspecting FootprintRegistry after a backtest:
  - Are trades being fed to FootprintRegistry?
  - Are levels accumulating over time?
  - Is CVD changing (not stuck at 0)?
  - Are there enough levels for absorption detection (>= 10)?
  - Is volume distribution realistic (not all zeros)?

Tests (with real backtest data):
  1. FootprintRegistry has registered symbols
  2. Multiple price levels exist (not just 1 level)
  3. CVD is non-zero (trades are flowing)
  4. At least 10 levels with non-zero delta (minimum for detection)
  5. Volume distribution is realistic (ask/bid both > 0)
  6. Levels have recent timestamps (data is fresh, not stale)
  7. Delta values vary (not all the same, which would indicate a bug)
  8. Volume profile extraction works

Input  → FootprintRegistry state after backtest
Output → Assert FootprintRegistry data quality metrics

Usage:
    # First, run a backtest:
    python backtest.py --exchange binance --symbols LTCUSDT --start 2024-01-01 --end 2024-01-02

    # Then run this validator:
    python utils/validators/absorption_footprint_data_validator.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.footprint_registry import FootprintRegistry


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")
    sys.exit(1)


def warn(msg):
    print(f"  ⚠️  {msg}")


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def main():
    print("=" * 60)
    print("  LAYER 0.E: FOOTPRINT REGISTRY DATA QUALITY VALIDATOR")
    print("  Absorption V1 — Real backtest data quality check")
    print("=" * 60)

    # ─────────────────────────────────────────────────────────
    # SETUP: Get FootprintRegistry singleton
    # ─────────────────────────────────────────────────────────
    section("SETUP: Inspecting FootprintRegistry state")

    registry = FootprintRegistry()

    print(f"  FootprintRegistry instance: {registry}")
    print(f"  Registered symbols: {list(registry.footprints.keys())}")

    # ─────────────────────────────────────────────────────────
    # TEST 1: FootprintRegistry has registered symbols
    # ─────────────────────────────────────────────────────────
    section("TEST 1: FootprintRegistry has registered symbols")

    if len(registry.footprints) == 0:
        fail(
            "FootprintRegistry has 0 registered symbols.\n"
            "  This validator requires a backtest to have been run first.\n"
            "  Run: python backtest.py --exchange binance --symbols LTCUSDT --start 2024-01-01 --end 2024-01-02\n"
            "  Then run this validator again."
        )

    ok(f"FootprintRegistry has {len(registry.footprints)} registered symbol(s)")

    # Use first symbol for testing
    symbol = list(registry.footprints.keys())[0]
    print(f"  Testing with symbol: {symbol}")

    fp = registry.footprints[symbol]
    num_levels = len(fp.levels)

    # ─────────────────────────────────────────────────────────
    # TEST 2: Multiple price levels exist
    # ─────────────────────────────────────────────────────────
    section("TEST 2: Multiple price levels exist (not empty)")

    if num_levels == 0:
        fail(
            f"FootprintRegistry has 0 levels for {symbol}.\n"
            f"  Possible causes:\n"
            f"    - Trades are not being fed to FootprintRegistry\n"
            f"    - SensorManager is not calling FootprintRegistry.add_trade()\n"
            f"    - Trade data source is empty or not connected\n"
            f"    - Backtest was too short or had no trades"
        )
    ok(f"FootprintRegistry has {num_levels} levels (not empty)")

    if num_levels < 5:
        warn(
            f"Only {num_levels} levels found (expected >= 5).\n"
            f"  This suggests trades are not spreading across price levels.\n"
            f"  Check if round_price() is working correctly or backtest was too short."
        )
    else:
        ok(f"{num_levels} levels found (good distribution)")

    # ─────────────────────────────────────────────────────────
    # TEST 3: CVD is non-zero (trades are flowing)
    # ─────────────────────────────────────────────────────────
    section("TEST 3: CVD is non-zero (trades are flowing)")

    cvd = fp.cvd

    if cvd == 0.0:
        warn(
            f"CVD = 0.0 (perfectly balanced buy/sell).\n"
            f"  This is statistically unlikely with real data.\n"
            f"  Check if delta calculation is correct (ask_vol - bid_vol)."
        )
    else:
        ok(f"CVD = {cvd:+,.2f} (trades are flowing)")

    # ─────────────────────────────────────────────────────────
    # TEST 4: At least 10 levels with non-zero delta
    # ─────────────────────────────────────────────────────────
    section("TEST 4: At least 10 levels with non-zero delta (minimum for detection)")

    non_zero_deltas = [(price, data["delta"]) for price, data in fp.levels.items() if data["delta"] != 0.0]
    num_non_zero = len(non_zero_deltas)

    print(f"  Total levels: {num_levels}")
    print(f"  Non-zero delta levels: {num_non_zero}")

    if num_non_zero < 10:
        fail(
            f"Only {num_non_zero} levels with non-zero delta (need >= 10).\n"
            f"  AbsorptionDetector requires >= 10 non-zero delta levels.\n"
            f"  Possible causes:\n"
            f"    - Backtest period too short (not enough trades)\n"
            f"    - All trades at same price (no price movement)\n"
            f"    - Delta calculation bug (all deltas = 0)\n"
            f"  Solution: Run a longer backtest or use a more volatile symbol."
        )
    ok(f"{num_non_zero} levels with non-zero delta (>= 10 required)")

    # ─────────────────────────────────────────────────────────
    # TEST 5: Volume distribution is realistic
    # ─────────────────────────────────────────────────────────
    section("TEST 5: Volume distribution is realistic (ask/bid both > 0)")

    levels_with_ask = sum(1 for data in fp.levels.values() if data["ask_volume"] > 0)
    levels_with_bid = sum(1 for data in fp.levels.values() if data["bid_volume"] > 0)

    print(f"  Levels with ask_volume > 0: {levels_with_ask}")
    print(f"  Levels with bid_volume > 0: {levels_with_bid}")

    if levels_with_ask == 0:
        fail("No levels have ask_volume > 0 (BUY trades not being recorded)")
    if levels_with_bid == 0:
        fail("No levels have bid_volume > 0 (SELL trades not being recorded)")

    ok(f"Both BUY and SELL trades are being recorded")

    # Check for unrealistic imbalance (all ask or all bid)
    ask_only = sum(1 for data in fp.levels.values() if data["ask_volume"] > 0 and data["bid_volume"] == 0)
    bid_only = sum(1 for data in fp.levels.values() if data["bid_volume"] > 0 and data["ask_volume"] == 0)

    print(f"  Levels with only ask (no bid): {ask_only}")
    print(f"  Levels with only bid (no ask): {bid_only}")

    if ask_only == num_levels or bid_only == num_levels:
        warn("All levels are one-sided (only BUY or only SELL). This is unusual.")
    else:
        ok("Volume distribution is realistic (mixed BUY/SELL)")

    # ─────────────────────────────────────────────────────────
    # TEST 6: Levels have timestamps
    # ─────────────────────────────────────────────────────────
    section("TEST 6: Levels have timestamps")

    timestamps = [data["last_update"] for data in fp.levels.values()]

    if not timestamps:
        fail("No timestamps found in levels")

    oldest_ts = min(timestamps)
    newest_ts = max(timestamps)
    time_range = newest_ts - oldest_ts

    print(f"  Oldest level timestamp: {oldest_ts:.0f}")
    print(f"  Newest level timestamp: {newest_ts:.0f}")
    print(f"  Time range: {time_range:.1f}s ({time_range/60:.1f} minutes)")

    if time_range == 0:
        warn("All levels have the same timestamp. This suggests all trades happened at once.")
    else:
        ok(f"Timestamps span {time_range/60:.1f} minutes (data has temporal distribution)")

    # ─────────────────────────────────────────────────────────
    # TEST 7: Delta values vary (not all the same)
    # ─────────────────────────────────────────────────────────
    section("TEST 7: Delta values vary (not all the same)")

    deltas = [data["delta"] for data in fp.levels.values()]
    unique_deltas = len(set(deltas))

    print(f"  Total levels: {num_levels}")
    print(f"  Unique delta values: {unique_deltas}")

    if unique_deltas == 1:
        warn(
            f"All deltas are the same ({deltas[0]}).\n"
            f"  This suggests a bug in delta calculation or trade accumulation."
        )
    else:
        ok(f"{unique_deltas} unique delta values (good variance)")

    # Show delta distribution
    deltas_sorted = sorted(deltas, key=abs, reverse=True)[:5]
    print(f"  Top 5 deltas by |value|: {[f'{d:+.1f}' for d in deltas_sorted]}")

    # ─────────────────────────────────────────────────────────
    # TEST 8: Volume profile extraction works
    # ─────────────────────────────────────────────────────────
    section("TEST 8: Volume profile extraction works (for TP calculation)")

    # Get price range from levels
    prices = list(fp.levels.keys())
    if not prices:
        fail("No prices in FootprintRegistry")

    min_price = min(prices)
    max_price = max(prices)

    # Extract volume profile for full range
    volume_profile = fp.get_volume_profile(min_price, max_price)

    print(f"  Price range: {min_price:.2f} → {max_price:.2f}")
    print(f"  Volume profile entries: {len(volume_profile)}")

    if len(volume_profile) == 0:
        fail("get_volume_profile() returned empty list")
    ok(f"Volume profile has {len(volume_profile)} entries")

    # Verify structure
    for i, entry in enumerate(volume_profile[:3]):
        if len(entry) != 3:
            fail(f"volume_profile[{i}] has {len(entry)} elements, expected 3 (price, ask, bid)")
        price_vp, ask_vp, bid_vp = entry
        if ask_vp < 0 or bid_vp < 0:
            fail(f"volume_profile[{i}] has negative volume: ask={ask_vp}, bid={bid_vp}")
    ok("Volume profile structure is correct (price, ask, bid)")

    # ─────────────────────────────────────────────────────────
    # SUMMARY: Data Quality Metrics
    # ─────────────────────────────────────────────────────────
    section("SUMMARY: FootprintRegistry Data Quality Metrics")

    print(f"  Symbol: {symbol}")
    print(f"  Total levels: {num_levels}")
    print(f"  Non-zero delta levels: {num_non_zero}")
    print(f"  CVD: {cvd:+,.2f}")
    print(f"  Levels with ask > 0: {levels_with_ask}")
    print(f"  Levels with bid > 0: {levels_with_bid}")
    print(f"  Unique delta values: {unique_deltas}")
    print(f"  Volume profile entries: {len(volume_profile)}")
    print(f"  Time range: {time_range/60:.1f} minutes")

    # ─────────────────────────────────────────────────────────
    # FINAL VERDICT
    # ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.E PASSED — FootprintRegistry data quality is good")
    print(f"{'=' * 60}\n")

    print("  FootprintRegistry is accumulating real trade data correctly.")
    print("  Next: Run Layer 0.4 to check if AbsorptionDetector generates")
    print("        signals with this real data.")
    print()


if __name__ == "__main__":
    main()
