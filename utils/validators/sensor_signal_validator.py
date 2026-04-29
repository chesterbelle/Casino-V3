"""
Sensor Signal Generation Validator
-----------------------------------
Validates that active sensors generate signals with real backtest data.

This validator exposes input/output data for debugging sensor logic:
- Input: Footprint data, candle data, tick data
- Processing: Candidates found, metrics calculated, guardian decisions
- Output: Signals generated

Critical for detecting:
- Sensors not being called by SensorManager
- Sensors with filters too strict (0 signals)
- Integration issues between sensors and workers
- Logic errors in sensor detection algorithms

Usage:
    python -m utils.validators.sensor_signal_validator
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from collections import defaultdict

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from config.sensors import ACTIVE_SENSORS
from core.footprint_registry import footprint_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)

logger = logging.getLogger("SensorSignalValidator")


class SensorSignalValidator:
    """
    Validates that active sensors generate signals with real backtest data.

    Exposes input/output data for debugging sensor logic without running full bot.
    """

    def __init__(self, dataset_path: str, symbol: str, db_path: str = "data/historian.db"):
        self.dataset_path = dataset_path
        self.symbol = symbol
        self.db_path = db_path

        # Diagnostic data collection
        self.sensor_diagnostics = defaultdict(
            lambda: {
                "calls": 0,
                "candidates_found": 0,
                "candidates_rejected": defaultdict(int),
                "signals_generated": 0,
                "sample_inputs": [],
                "sample_rejections": [],
                "sample_signals": [],
            }
        )

    async def run_validation(self) -> bool:
        """
        Run backtest and validate signal generation with diagnostics.
        """
        logger.info("=" * 80)
        logger.info("SENSOR SIGNAL GENERATION VALIDATOR")
        logger.info("=" * 80)
        logger.info(f"Dataset: {self.dataset_path}")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Active Sensors: {sum(1 for v in ACTIVE_SENSORS.values() if v)}")
        logger.info("=" * 80)

        # Clean database before backtest
        self._clean_database()

        # Patch AbsorptionDetector to collect diagnostics
        self._patch_absorption_detector()

        # Run backtest using backtest.py
        logger.info("🚀 Starting backtest replay...")
        start_time = time.time()

        try:
            # Import here to avoid circular dependencies
            from backtest import run_backtest

            # Mock sys.argv to pass arguments to backtest
            original_argv = sys.argv
            sys.argv = [
                "backtest.py",
                "--data",
                self.dataset_path,
                "--symbol",
                self.symbol,
                "--depth-db",
                self.db_path,
                "--audit",  # Audit mode (no trades)
            ]

            # Run backtest
            await run_backtest()

            # Restore original argv
            sys.argv = original_argv

        except Exception as e:
            logger.error(f"❌ Backtest failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        duration = time.time() - start_time
        logger.info(f"✅ Backtest completed in {duration:.2f}s")

        # Analyze signals from database
        db_passed = self._analyze_signals()

        # Show diagnostics
        self._show_diagnostics()

        return db_passed

    def _patch_absorption_detector(self):
        """
        Patch AbsorptionDetector to collect diagnostic data.
        """
        from sensors.absorption.absorption_detector import AbsorptionDetector

        original_analyze = AbsorptionDetector._analyze_absorption
        validator = self

        def patched_analyze(self, symbol: str, timestamp: float):
            """Patched _analyze_absorption with diagnostics."""
            sensor_name = "AbsorptionDetector"
            diag = validator.sensor_diagnostics[sensor_name]
            diag["calls"] += 1

            # Get footprint data for diagnostics
            footprint = footprint_registry.get_footprint(symbol)

            # Sample input data (every 100 calls)
            if diag["calls"] % 100 == 0 and footprint:
                level_count = len(footprint.levels)
                deltas = [data.get("delta", 0) for data in footprint.levels.values()]
                non_zero_deltas = [d for d in deltas if abs(d) > 0]

                input_sample = {
                    "call_number": diag["calls"],
                    "timestamp": timestamp,
                    "footprint_levels": level_count,
                    "non_zero_deltas": len(non_zero_deltas),
                    "max_delta": max(abs(d) for d in non_zero_deltas) if non_zero_deltas else 0,
                    "avg_delta": sum(abs(d) for d in non_zero_deltas) / len(non_zero_deltas) if non_zero_deltas else 0,
                }
                diag["sample_inputs"].append(input_sample)

            # Call original method
            result = original_analyze(self, symbol, timestamp)

            if result:
                diag["signals_generated"] += 1
                # Sample signal (first 5)
                if len(diag["sample_signals"]) < 5:
                    diag["sample_signals"].append(
                        {
                            "direction": result.get("direction"),
                            "z_score": result.get("z_score"),
                            "concentration": result.get("concentration"),
                            "noise": result.get("noise"),
                            "level": result.get("level"),
                        }
                    )

            return result

        # Apply patch
        AbsorptionDetector._analyze_absorption = patched_analyze
        logger.info("🔧 Patched AbsorptionDetector for diagnostics collection")

    def _clean_database(self):
        """Clean database before backtest."""
        if os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("DELETE FROM signals")
                conn.execute("DELETE FROM price_samples")
                conn.execute("DELETE FROM decision_traces")
                conn.commit()
                conn.close()
                logger.info("🧹 Database cleaned")
            except Exception as e:
                logger.warning(f"⚠️ Could not clean database: {e}")

    def _analyze_signals(self) -> bool:
        """
        Analyze signals from database.
        """
        logger.info("\n" + "=" * 80)
        logger.info("SIGNAL GENERATION ANALYSIS (DATABASE)")
        logger.info("=" * 80)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get total signal count
            cursor.execute("SELECT COUNT(*) FROM signals")
            total_signals = cursor.fetchone()[0]
            logger.info(f"Total Signals: {total_signals}")
            logger.info("")

            # Get signals by setup_type (which identifies the sensor/strategy)
            cursor.execute(
                """
                SELECT setup_type, COUNT(*) as count
                FROM signals
                GROUP BY setup_type
                ORDER BY count DESC
            """
            )
            signals_by_sensor = dict(cursor.fetchall())

            conn.close()

        except Exception as e:
            logger.error(f"❌ Could not read database: {e}")
            return False

        # Report by sensor
        active_sensors = [name for name, active in ACTIVE_SENSORS.items() if active]
        sensors_with_signals = set(signals_by_sensor.keys())
        sensors_without_signals = set(active_sensors) - sensors_with_signals

        if signals_by_sensor:
            logger.info("Signals by Sensor:")
            for sensor_name in sorted(signals_by_sensor.keys()):
                count = signals_by_sensor[sensor_name]
                logger.info(f"  {sensor_name:40s}: {count:4d} signals")

        if sensors_without_signals:
            logger.warning("")
            logger.warning("⚠️ Active Sensors with ZERO signals:")
            for sensor_name in sorted(sensors_without_signals):
                logger.warning(f"  {sensor_name:40s}: 0 signals ❌")

        # Validation
        logger.info("\n" + "=" * 80)
        logger.info("VALIDATION RESULTS")
        logger.info("=" * 80)

        failures = []

        # Check critical sensors (Absorption V1)
        critical_sensors = [name for name, active in ACTIVE_SENSORS.items() if active and "Absorption" in name]

        for sensor_name in critical_sensors:
            if sensor_name not in sensors_with_signals:
                logger.error(f"❌ CRITICAL: {sensor_name} generated 0 signals!")
                failures.append(sensor_name)
            else:
                count = signals_by_sensor[sensor_name]
                if count < 5:
                    logger.warning(f"⚠️ WARNING: {sensor_name} generated only {count} signals (< 5)")
                    logger.warning(f"   This may indicate overly strict filters")
                else:
                    logger.info(f"✅ {sensor_name}: {count} signals")

        # Summary
        if failures:
            logger.error(f"\n❌ VALIDATION FAILED: {len(failures)} critical sensors generated 0 signals")
            logger.error(f"Failed sensors: {', '.join(failures)}")
            return False
        else:
            logger.info(f"\n✅ VALIDATION PASSED: All critical sensors generated signals")
            return True

    def _show_diagnostics(self):
        """
        Show diagnostic data collected during backtest.
        """
        logger.info("\n" + "=" * 80)
        logger.info("SENSOR DIAGNOSTICS (INPUT/OUTPUT ANALYSIS)")
        logger.info("=" * 80)

        for sensor_name, diag in self.sensor_diagnostics.items():
            logger.info(f"\n📊 {sensor_name}")
            logger.info(f"   Calls: {diag['calls']}")
            logger.info(f"   Signals Generated: {diag['signals_generated']}")

            # Show sample inputs
            if diag["sample_inputs"]:
                logger.info(f"\n   Sample Inputs (every 100 calls):")
                for sample in diag["sample_inputs"][:5]:
                    logger.info(f"      Call #{sample['call_number']}:")
                    logger.info(f"         Footprint Levels: {sample['footprint_levels']}")
                    logger.info(f"         Non-Zero Deltas: {sample['non_zero_deltas']}")
                    logger.info(f"         Max Delta: {sample['max_delta']:.2f}")
                    logger.info(f"         Avg Delta: {sample['avg_delta']:.2f}")

            # Show sample signals
            if diag["sample_signals"]:
                logger.info(f"\n   Sample Signals Generated:")
                for i, signal in enumerate(diag["sample_signals"], 1):
                    logger.info(f"      Signal #{i}:")
                    logger.info(f"         Direction: {signal['direction']}")
                    logger.info(f"         Z-Score: {signal['z_score']:.2f}")
                    logger.info(f"         Concentration: {signal['concentration']:.2f}")
                    logger.info(f"         Noise: {signal['noise']:.2f}")
                    logger.info(f"         Level: {signal['level']:.2f}")

            # Show rejection reasons if no signals
            if diag["signals_generated"] == 0 and diag["calls"] > 0:
                logger.warning(f"\n   ⚠️ No signals generated despite {diag['calls']} calls")
                logger.warning(f"      Possible causes:")
                logger.warning(f"         1. No candidates found (footprint data insufficient)")
                logger.warning(f"         2. All candidates rejected by guardians")
                logger.warning(f"         3. Filters too strict")


async def main():
    # Default dataset
    dataset_path = "tests/validation/ltc_24h_audit.csv"
    symbol = "LTC/USDT:USDT"
    db_path = "data/historian.db"

    # Allow override via args
    if len(sys.argv) > 1:
        dataset_path = sys.argv[1]
    if len(sys.argv) > 2:
        symbol = sys.argv[2]
    if len(sys.argv) > 3:
        db_path = sys.argv[3]

    validator = SensorSignalValidator(dataset_path, symbol, db_path)
    passed = await validator.run_validation()

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
