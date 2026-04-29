"""
Absorption V1 Diagnostic Tool.

Analyzes why AbsorptionDetector is not generating signals.
Checks:
1. Footprint data availability
2. Extreme delta candidates
3. Quality filter pass rates (z-score, concentration, noise)
"""

import asyncio
import logging
import sys
from collections import defaultdict

# Add project root to path
sys.path.insert(0, ".")

from core.footprint_registry import footprint_registry
from sensors.absorption.absorption_detector import AbsorptionDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def run_diagnostic():
    """Run diagnostic on AbsorptionDetector."""
    logger.info("🔍 Starting Absorption V1 Diagnostic...")

    # Initialize detector
    detector = AbsorptionDetector()
    detector.symbol = "LTC/USDT:USDT"

    # Run backtest to populate FootprintRegistry
    logger.info("📊 Running backtest to populate FootprintRegistry...")
    import contextlib

    # Temporarily redirect stdout to suppress backtest logs
    import io

    from backtest import main as backtest_main

    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        await backtest_main()

    logger.info("✅ Backtest complete. Analyzing FootprintRegistry...")

    # Get footprint
    symbol = "LTC/USDT:USDT"
    footprint = footprint_registry.get_footprint(symbol)

    if not footprint:
        logger.error(f"❌ No footprint found for {symbol}")
        return

    logger.info(f"📊 Footprint has {len(footprint.levels)} levels")

    if len(footprint.levels) < 10:
        logger.warning(f"⚠️ Insufficient footprint data: {len(footprint.levels)} levels (need >= 10)")
        return

    # Analyze deltas
    deltas = []
    for level, data in footprint.levels.items():
        delta = data["delta"]
        if abs(delta) > 0:
            deltas.append((level, delta, data["ask_volume"], data["bid_volume"]))

    logger.info(f"📊 Found {len(deltas)} levels with non-zero delta")

    if not deltas:
        logger.warning("⚠️ No levels with non-zero delta found")
        return

    # Sort by absolute delta
    deltas.sort(key=lambda x: abs(x[1]), reverse=True)

    # Show top 10 deltas
    logger.info("\n📊 Top 10 Extreme Deltas:")
    for i, (level, delta, ask_vol, bid_vol) in enumerate(deltas[:10]):
        logger.info(f"  {i+1}. Level {level}: delta={delta:.2f}, ask={ask_vol:.2f}, bid={bid_vol:.2f}")

    # Test quality filters on top candidates
    logger.info("\n🔍 Testing Quality Filters on Top 10 Candidates:")

    stats = {
        "total_candidates": 0,
        "passed_magnitude": 0,
        "passed_velocity": 0,
        "passed_noise": 0,
        "passed_all": 0,
    }

    for i, (level, delta, ask_vol, bid_vol) in enumerate(deltas[:10]):
        stats["total_candidates"] += 1

        # Filter 1: Magnitude (z-score)
        z_score = detector._calculate_z_score(symbol, delta, 0.0)
        passed_magnitude = abs(z_score) >= detector.z_score_min

        # Filter 2: Velocity (concentration)
        concentration = detector._calculate_concentration(footprint, level, 0.0)
        passed_velocity = concentration >= detector.concentration_min

        # Filter 3: Noise
        noise = detector._calculate_noise(ask_vol, bid_vol, delta)
        passed_noise = noise <= detector.noise_max

        passed_all = passed_magnitude and passed_velocity and passed_noise

        if passed_magnitude:
            stats["passed_magnitude"] += 1
        if passed_velocity:
            stats["passed_velocity"] += 1
        if passed_noise:
            stats["passed_noise"] += 1
        if passed_all:
            stats["passed_all"] += 1

        status = "✅ PASS" if passed_all else "❌ FAIL"
        logger.info(
            f"  {i+1}. Level {level}: {status} | "
            f"z={z_score:.2f} ({'✅' if passed_magnitude else '❌'}), "
            f"conc={concentration:.2f} ({'✅' if passed_velocity else '❌'}), "
            f"noise={noise:.2f} ({'✅' if passed_noise else '❌'})"
        )

    # Summary
    logger.info("\n📊 Filter Pass Rates:")
    logger.info(f"  Total Candidates: {stats['total_candidates']}")
    logger.info(
        f"  Magnitude (z-score >= {detector.z_score_min}): {stats['passed_magnitude']}/{stats['total_candidates']} ({stats['passed_magnitude']/stats['total_candidates']*100:.1f}%)"
    )
    logger.info(
        f"  Velocity (conc >= {detector.concentration_min}): {stats['passed_velocity']}/{stats['total_candidates']} ({stats['passed_velocity']/stats['total_candidates']*100:.1f}%)"
    )
    logger.info(
        f"  Noise (<= {detector.noise_max}): {stats['passed_noise']}/{stats['total_candidates']} ({stats['passed_noise']/stats['total_candidates']*100:.1f}%)"
    )
    logger.info(
        f"  All Filters: {stats['passed_all']}/{stats['total_candidates']} ({stats['passed_all']/stats['total_candidates']*100:.1f}%)"
    )

    # Recommendations
    logger.info("\n💡 Recommendations:")
    if stats["passed_all"] == 0:
        if stats["passed_magnitude"] == 0:
            logger.info(f"  ⚠️ Z-score threshold too high ({detector.z_score_min}). Consider lowering to 2.0-2.5")
        if stats["passed_velocity"] == 0:
            logger.info(
                f"  ⚠️ Concentration threshold too high ({detector.concentration_min}). Consider lowering to 0.50-0.60"
            )
        if stats["passed_noise"] == 0:
            logger.info(f"  ⚠️ Noise threshold too low ({detector.noise_max}). Consider raising to 0.25-0.30")
    else:
        logger.info(f"  ✅ {stats['passed_all']} candidates passed all filters. Detector should be generating signals.")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
