"""
Quick diagnostic test for AbsorptionDetector.
Tests the sensor logic directly without running full backtest.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

import time

from core.footprint_registry import footprint_registry
from sensors.absorption.absorption_detector import AbsorptionDetector

# Initialize
detector = AbsorptionDetector()
symbol = "LTC/USDT:USDT"
tick_size = 0.01

# Register symbol
footprint_registry.register_symbol(symbol, tick_size)

# Simulate some trades to build footprint
print("=" * 80)
print("ABSORPTION DETECTOR DIAGNOSTICS")
print("=" * 80)
print(f"\n1. Building footprint with sample trades...")

timestamp = time.time()

# Add 100 trades with varying deltas
trades = [
    (78.50, 100, "BUY"),
    (78.50, 50, "SELL"),
    (78.51, 200, "BUY"),
    (78.51, 30, "SELL"),
    (78.52, 500, "BUY"),  # Strong buy absorption candidate
    (78.52, 50, "SELL"),
    (78.53, 100, "BUY"),
    (78.53, 80, "SELL"),
    (78.49, 50, "BUY"),
    (78.49, 400, "SELL"),  # Strong sell absorption candidate
    (78.48, 100, "BUY"),
    (78.48, 150, "SELL"),
]

for price, volume, side in trades:
    footprint_registry.on_trade(symbol, price, volume, side, timestamp)
    timestamp += 0.1

# Get footprint state
footprint = footprint_registry.get_footprint(symbol)
print(f"   Footprint levels: {len(footprint.levels)}")

# Show footprint data
print(f"\n2. Footprint Data (Input):")
for level in sorted(footprint.levels.keys(), reverse=True)[:10]:
    data = footprint.levels[level]
    print(
        f"   Level {level:.2f}: Delta={data['delta']:+8.2f}, Ask={data['ask_volume']:6.2f}, Bid={data['bid_volume']:6.2f}"
    )

# Test _find_extreme_deltas
print(f"\n3. Finding Extreme Deltas...")
candidates = detector._find_extreme_deltas(footprint, timestamp)
print(f"   Candidates found: {len(candidates)}")
for level, delta, ask_vol, bid_vol in candidates:
    print(f"      Level {level:.2f}: Delta={delta:+8.2f}, Ask={ask_vol:6.2f}, Bid={bid_vol:6.2f}")

# Test guardians on each candidate
if candidates:
    print(f"\n4. Testing Guardians on Candidates:")
    for level, delta, ask_vol, bid_vol in candidates:
        print(f"\n   Candidate: Level {level:.2f}, Delta={delta:+.2f}")

        # Calculate metrics
        z_score = detector._calculate_z_score(symbol, delta, timestamp)
        concentration = detector._calculate_concentration(footprint, level, timestamp)
        noise = detector._calculate_noise(ask_vol, bid_vol, delta)

        print(f"      Metrics:")
        print(f"         Z-Score: {z_score:.2f} (threshold: {detector.z_score_min})")
        print(f"         Concentration: {concentration:.2f} (threshold: {detector.concentration_min})")
        print(f"         Noise: {noise:.2f} (threshold: {detector.noise_max})")

        # Test guardians
        mag_pass = detector._validate_magnitude(z_score)
        vel_pass = detector._validate_velocity(concentration)
        noise_pass = detector._validate_noise(noise)

        print(f"      Guardian Results:")
        print(f"         Magnitude: {'✅ PASS' if mag_pass else '❌ FAIL'}")
        print(f"         Velocity: {'✅ PASS' if vel_pass else '❌ FAIL'}")
        print(f"         Noise: {'✅ PASS' if noise_pass else '❌ FAIL'}")

        if mag_pass and vel_pass and noise_pass:
            print(f"      ✅ ALL GUARDIANS PASSED - Would generate signal")
        else:
            print(f"      ❌ REJECTED")

# Test full analyze method
print(f"\n5. Testing Full _analyze_absorption():")
candle_data = {
    "1m": {
        "symbol": symbol,
        "timestamp": timestamp,
        "close": 78.50,
    }
}

signal = detector.calculate(candle_data)
if signal:
    print(f"   ✅ Signal Generated:")
    print(f"      Direction: {signal['direction']}")
    print(f"      Level: {signal['level']:.2f}")
    print(f"      Z-Score: {signal['z_score']:.2f}")
    print(f"      Concentration: {signal['concentration']:.2f}")
    print(f"      Noise: {signal['noise']:.2f}")
else:
    print(f"   ❌ No signal generated")

print(f"\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
