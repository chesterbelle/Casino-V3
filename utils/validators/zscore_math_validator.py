#!/usr/bin/env python3
"""
Validator for Phase 2: VolatilityRegime (RollingZScore)
Verifies O(1) sliding window math, mean/std stability, and Z-Score outlier detection.
"""
import math
import os
import sys

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from sensors.quant.volatility_regime import RollingZScore


def ok(msg):
    print(f"✅ {msg}")


def fail(msg):
    print(f"❌ {msg}")
    sys.exit(1)


def main():
    print("=" * 60)
    print(" STRATEGY 2.0 VALIDATOR: VOLATILITY REGIME (Z-SCORES)")
    print("=" * 60)

    # 1. Basic Math & Initialization
    tracker = RollingZScore(window_size=5)
    assert tracker.is_ready is False, "Tracker should not be ready initially"
    assert tracker.mean == 0.0, "Initial mean should be 0.0"

    # 2. Window Filling & Mean Calculation
    values = [10.0, 12.0, 10.0, 8.0, 10.0]
    for v in values:
        tracker.update(v)

    # Mean = 50 / 5 = 10.0
    if not math.isclose(tracker.mean, 10.0, rel_tol=1e-5):
        fail(f"Math Error: Mean is {tracker.mean}, expected 10.0")
    ok("Basic Mean Calculation correct")

    # Variance = E[X^2] - E[X]^2
    # X^2 = 100, 144, 100, 64, 100 => 508 / 5 = 101.6
    # Var = 101.6 - 100 = 1.6
    # StdDev = sqrt(1.6) ~= 1.2649

    # 3. Z-Score Calculation (Normal values)
    z1 = tracker.get_zscore(12.5)  # (12.5 - 10) / 1.2649 = 1.97
    if not (1.9 < z1 < 2.0):
        fail(f"Math Error: Z-Score for 12.5 is {z1}, expected ~1.97")
    ok("Normal Z-Score calculation correct")

    # 4. Outlier Detection (Z > 3.0)
    z_outlier = tracker.get_zscore(15.0)  # (15.0 - 10) / 1.2649 = 3.95
    if z_outlier <= 3.0:
        fail(f"Logic Error: 15.0 should be an outlier (Z > 3.0), got {z_outlier}")
    ok(f"Outlier detected successfully: Z={z_outlier:.2f}")

    # 5. Sliding Window (O(1) updates)
    # Add a new value, pushing out the first 10.0
    tracker.update(20.0)
    # Window is now: [12.0, 10.0, 8.0, 10.0, 20.0] -> Sum = 60 -> Mean = 12.0
    if not math.isclose(tracker.mean, 12.0, rel_tol=1e-5):
        fail(f"Sliding Window Error: Mean is {tracker.mean}, expected 12.0")
    ok("O(1) Sliding Window queue flush correct")

    # 6. Negative values & Extreme Zero crossing
    tracker_neg = RollingZScore(window_size=3)
    tracker_neg.update(-5.0)
    tracker_neg.update(-10.0)
    tracker_neg.update(-15.0)
    if not math.isclose(tracker_neg.mean, -10.0, rel_tol=1e-5):
        fail(f"Negative Number Error: Mean is {tracker_neg.mean}, expected -10.0")

    z_neg = tracker_neg.get_zscore(-25.0)
    if z_neg >= 0:
        fail(f"Z-Score Direction Error: Expected negative Z-Score, got {z_neg}")
    ok("Negative value handling correct")

    print("\n✅ STRATEGY 2.0 VALIDATOR: VOLATILITY REGIME PASSED\n")


if __name__ == "__main__":
    main()
