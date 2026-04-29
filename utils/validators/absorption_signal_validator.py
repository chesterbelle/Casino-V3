#!/usr/bin/env python3
"""
Layer 0.D: Signal Generation Validator (V2)
----------------------------------------
In V2, AbsorptionDetector returns CANDIDATES via on_candle(),
and AbsorptionReversalGuardian confirms them.
This script validates that AbsorptionDetector.on_candle() properly
outputs a candidate dict when conditions are met.

Usage:
    python utils/validators/absorption_signal_validator.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.footprint_registry import FootprintData, footprint_registry
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


def inject_footprint(symbol: str, levels: dict, tick_size: float = 0.01):
    footprint_registry.register_symbol(symbol, tick_size)
    fp = footprint_registry.footprints[symbol]
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


def main():
    print("=" * 60)
    print("  LAYER 0.D: CANDIDATE GENERATION VALIDATOR (V2)")
    print("=" * 60)

    footprint_registry.reset()
    detector = AbsorptionDetector()
    detector.z_score_min = 1.5
    detector.concentration_min = 0.40
    detector.noise_max = 0.40

    ts = 1000.0

    section("TEST 1: SELL absorption → Candidate")
    sym_sell = "SELL_TEST/USDT"
    levels_sell = {78.40 + i * 0.01: (55.0, 45.0) for i in range(20)}
    levels_sell[78.50] = (10.0, 990.0)  # delta=-980
    inject_footprint(sym_sell, levels_sell)

    candidate = detector.on_candle(sym_sell, ts, close_price=78.50, open_price=78.50, high_price=78.55, low_price=78.49)

    if not candidate:
        fail("Expected candidate, got None")

    if candidate["direction"] != "SELL_EXHAUSTION":
        fail(f"direction={candidate['direction']}, expected SELL_EXHAUSTION")
    ok("direction = SELL_EXHAUSTION ✓")

    if candidate["side"] != "LONG":
        fail(f"side={candidate['side']}, expected LONG")
    ok("side = LONG ✓")

    section("TEST 2: Flat footprint → None")
    sym_flat = "FLAT_TEST/USDT"
    levels_flat = {78.40 + i * 0.01: (50.0, 50.0) for i in range(20)}
    inject_footprint(sym_flat, levels_flat)

    candidate_flat = detector.on_candle(
        sym_flat, ts, close_price=78.50, open_price=78.50, high_price=78.55, low_price=78.49
    )
    if candidate_flat is not None:
        fail("Expected None for flat footprint")
    ok("Flat footprint → None ✓")

    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.D PASSED — Candidate generation is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
