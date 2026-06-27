#!/usr/bin/env python3
"""
Layer 0.D: Signal Generation Validator (V2)
----------------------------------------
Validates that AbsorptionDetector.calculate() properly
outputs a signal dict when conditions are met.

Usage:
    python utils/validators/absorption_signal_validator.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.footprint_registry import FootprintData, footprint_registry
from decision.scenarios.tactical_absorption import AbsorptionDetector


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
    print("  LAYER 0.D: SIGNAL GENERATION VALIDATOR (V2)")
    print("=" * 60)

    footprint_registry.reset()
    detector = AbsorptionDetector()
    detector.z_score_min = 1.5
    detector.concentration_min = 0.40
    detector.noise_max = 0.40

    ts = 1000.0

    section("TEST 1: SELL absorption → Signal")
    sym_sell = "SELL_TEST/USDT"
    levels_sell = {78.40 + i * 0.01: (55.0, 45.0) for i in range(20)}
    levels_sell[78.50] = (10.0, 990.0)  # delta=-980
    inject_footprint(sym_sell, levels_sell)

    context_sell = {
        "1m": {"symbol": sym_sell, "timestamp": ts, "close": 78.50, "open": 78.50, "high": 78.55, "low": 78.49}
    }
    signal_sell = detector.calculate(context_sell)

    if not signal_sell:
        fail("Expected signal, got None")

    if signal_sell["metadata"]["direction"] != "SELL_EXHAUSTION":
        fail(f"direction={signal_sell['metadata']['direction']}, expected SELL_EXHAUSTION")
    ok("direction = SELL_EXHAUSTION ✓")

    if signal_sell["side"] != "LONG":
        fail(f"side={signal_sell['side']}, expected LONG")
    ok("side = LONG ✓")

    section("TEST 2: Flat footprint → None")
    sym_flat = "FLAT_TEST/USDT"
    levels_flat = {78.40 + i * 0.01: (50.0, 50.0) for i in range(20)}
    inject_footprint(sym_flat, levels_flat)

    context_flat = {
        "1m": {"symbol": sym_flat, "timestamp": ts, "close": 78.50, "open": 78.50, "high": 78.55, "low": 78.49}
    }
    signal_flat = detector.calculate(context_flat)
    if signal_flat is not None:
        fail("Expected None for flat footprint")
    ok("Flat footprint → None ✓")

    print(f"\n{'=' * 60}")
    print("  ✅ LAYER 0.D PASSED — Signal generation is correct")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
