#!/usr/bin/env python3
"""
Casino V3 - Training Pipeline
==============================

Unified pipeline for training and optimizing sensor parameters.

Phases:
1. download    - Download historical kline data from Binance
2. collect     - Run backtest to collect MFE/MAE data for each trade
3. optimize    - Optimize TP/SL parameters for each sensor/timeframe
4. validate    - Run validation backtest with optimized params
5. report      - Generate performance report

Usage:
    # Full pipeline
    python utils/training/train_pipeline.py --symbol LTCUSDT --days 30

    # Individual phases
    python utils/training/train_pipeline.py --phase download --symbol LTCUSDT --days 30
    python utils/training/train_pipeline.py --phase optimize --data data/raw/LTCUSDT_1m__30d.csv
    python utils/training/train_pipeline.py --phase validate --data data/raw/LTCUSDT_1m__30d.csv
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Setup paths
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("TrainPipeline")


class TrainingPipeline:
    """Unified training pipeline for Casino V3."""

    def __init__(self, symbol: str, interval: str = "1m", days: int = 30):
        self.symbol = symbol
        self.interval = interval
        self.days = days
        self.data_dir = ROOT / "data" / "raw"
        self.output_dir = ROOT / "config"
        self.results = {}
        self._data_file_override = None

    # =========================================================================
    # Phase 1: Download Data
    # =========================================================================
    def download(self) -> bool:
        """Download historical kline data from Binance."""
        logger.info(f"📥 Phase 1: Downloading {self.days} days of {self.symbol} {self.interval} data...")

        cmd = [
            sys.executable,
            str(ROOT / "utils" / "data" / "download_kline_dataset.py"),
            "--symbol",
            self.symbol,
            "--interval",
            self.interval,
            "--days",
            str(self.days),
            "--tag",
            f"{self.days}d",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"❌ Download failed: {result.stderr}")
            return False

        if not self.data_file.exists():
            logger.error(f"❌ Data file not created: {self.data_file}")
            return False

        # Count rows
        with open(self.data_file) as f:
            rows = sum(1 for _ in f) - 1  # Exclude header

        logger.info(f"✅ Downloaded {rows:,} candles to {self.data_file.name}")
        self.results["download"] = {"rows": rows, "file": str(self.data_file)}
        return True

    # =========================================================================
    # Phase 2: Collect MFE/MAE Data
    # =========================================================================
    def collect(self) -> bool:
        """Run backtest to collect MFE/MAE data for optimization."""
        logger.info(f"📊 Phase 2: Collecting MFE/MAE data via backtest...")

        if not self.data_file.exists():
            logger.error(f"❌ Data file not found: {self.data_file}")
            return False

        # Run collect_stats.py (Aggregator-Free)
        # This populates state/sensor_stats.json with simulated trade data for ALL sensors
        cmd = [
            sys.executable,
            str(ROOT / "utils" / "training" / "collect_stats.py"),
            f"--data={self.data_file}",
            f"--symbol={self.symbol}",
        ]

        logger.info(f"   Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=43200)

        if result.returncode != 0:
            logger.error(f"❌ Backtest failed: {result.stderr[-500:]}")
            return False

        # Parse results from output
        import re

        match = re.search(r"Wins / Losses\s*:\s*(\d+)\s*/\s*(\d+)", result.stdout)
        if match:
            wins, losses = int(match.group(1)), int(match.group(2))
            total = wins + losses
            logger.info(f"✅ Collected data from {total:,} trades ({wins} wins, {losses} losses)")
            self.results["collect"] = {"wins": wins, "losses": losses, "total": total}

        return True

    # =========================================================================
    # Phase 3: Optimize Parameters
    # =========================================================================
    def optimize(self) -> bool:
        """Optimize TP/SL parameters for each sensor/timeframe."""
        logger.info(f"🎯 Phase 3: Optimizing sensor parameters...")

        if not self.data_file.exists():
            logger.error(f"❌ Data file not found: {self.data_file}")
            return False

        # Run optimizer (uses --files argument)
        cmd = [sys.executable, str(ROOT / "utils" / "analysis" / "optimize_sensors.py"), "--files", str(self.data_file)]

        logger.info(f"   Running optimizer...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

        if result.returncode != 0:
            logger.error(f"❌ Optimization failed: {result.stderr[-500:]}")
            return False

        # Check output
        output_file = ROOT / "config" / "optimized_params.json"
        if output_file.exists():
            with open(output_file) as f:
                params = json.load(f)
            logger.info(f"✅ Optimized parameters for {len(params)} sensors saved to {output_file.name}")
            self.results["optimize"] = {"sensors": len(params)}
            return True

        logger.warning("⚠️ Optimization completed but no output file found")
        return False

    # =========================================================================
    # Phase 4: Validate
    # =========================================================================
    def validate(self) -> bool:
        """Run validation backtest with optimized parameters."""
        logger.info(f"✅ Phase 4: Running validation backtest...")

        if not self.data_file.exists():
            logger.error(f"❌ Data file not found: {self.data_file}")
            return False

        # Run backtest again (now with optimized params loaded from config)
        cmd = [sys.executable, str(ROOT / "backtest.py"), f"--data={self.data_file}", f"--symbol={self.symbol}"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode != 0:
            logger.error(f"❌ Validation failed: {result.stderr[-500:]}")
            return False

        # Parse and report results
        import re

        wins_match = re.search(r"Wins / Losses\s*:\s*(\d+)\s*/\s*(\d+)", result.stdout)
        pnl_match = re.search(r"PnL Total\s*:\s*([\+\-]?\d+\.?\d*)", result.stdout)

        if wins_match and pnl_match:
            wins, losses = int(wins_match.group(1)), int(wins_match.group(2))
            pnl = float(pnl_match.group(1))
            total = wins + losses
            wr = (wins / total * 100) if total > 0 else 0

            logger.info(f"📊 Validation Results:")
            logger.info(f"   Trades: {total} | Wins: {wins} | Losses: {losses}")
            logger.info(f"   Win Rate: {wr:.1f}%")
            logger.info(f"   PnL: {pnl:+.2f}")

            self.results["validate"] = {"wins": wins, "losses": losses, "total": total, "win_rate": wr, "pnl": pnl}

        return True

    # =========================================================================
    # Phase 5: Report
    # =========================================================================
    def report(self) -> bool:
        """Generate final training report."""
        logger.info(f"📝 Phase 5: Generating report...")

        report_file = ROOT / "logs" / f"training_report_{self.symbol}_{datetime.now():%Y%m%d_%H%M}.json"
        report_file.parent.mkdir(exist_ok=True)

        report = {
            "timestamp": datetime.now().isoformat(),
            "symbol": self.symbol,
            "interval": self.interval,
            "days": self.days,
            "results": self.results,
        }

        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"✅ Report saved to: {report_file}")
        return True

    # =========================================================================
    # Batch Processing
    # =========================================================================
    def run_batch(self, folder: Path, phases: list = None) -> bool:
        """Run pipeline on all CSV files in a folder sequentially."""
        csv_files = sorted(folder.glob("*.csv"))

        if not csv_files:
            logger.error(f"❌ No CSV files found in: {folder}")
            return False

        logger.info("=" * 60)
        logger.info("🚀 CASINO V3 BATCH TRAINING")
        logger.info("=" * 60)
        logger.info(f"   Folder: {folder}")
        logger.info(f"   Files: {len(csv_files)}")
        logger.info(f"   Phases: {', '.join(phases or ['collect', 'optimize', 'validate', 'report'])}")
        logger.info("=" * 60)

        all_results = {}

        for i, csv_file in enumerate(csv_files, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"📁 [{i}/{len(csv_files)}] Processing: {csv_file.name}")
            logger.info(f"{'='*60}")

            # Extract symbol from filename (e.g., LTCUSDT_1m__30d.csv -> LTC/USDT:USDT)
            import re

            match = re.match(r"([A-Z]+)(USDT)", csv_file.name)
            if match:
                base = match.group(1)
                self.symbol = f"{base}/USDT:USDT"  # CCXT format

            # Set data file
            self._data_file_override = csv_file

            # Run phases (skip download since we have the files)
            run_phases = phases or ["collect", "optimize", "validate", "report"]
            run_phases = [p for p in run_phases if p != "download"]  # Skip download

            success = self._run_phases(run_phases)

            all_results[csv_file.name] = {"success": success, "results": self.results.copy()}
            self.results = {}  # Reset for next file

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 BATCH SUMMARY")
        logger.info("=" * 60)

        for filename, result in all_results.items():
            status = "✅" if result["success"] else "❌"
            validate = result["results"].get("validate", {})
            pnl = validate.get("pnl", 0)
            wr = validate.get("win_rate", 0)
            logger.info(f"   {status} {filename}: WR={wr:.1f}% PnL={pnl:+.2f}")

        logger.info("=" * 60)

        # Save batch report
        report_file = ROOT / "logs" / f"batch_training_{datetime.now():%Y%m%d_%H%M}.json"
        report_file.parent.mkdir(exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(all_results, f, indent=2)
        logger.info(f"💾 Batch report saved to: {report_file}")

        return all(r["success"] for r in all_results.values())

    def _run_phases(self, phases: list) -> bool:
        """Run specified phases."""
        all_phases = ["download", "collect", "optimize", "validate", "report"]

        for phase in phases:
            if phase not in all_phases:
                logger.warning(f"⚠️ Unknown phase: {phase}")
                continue

            method = getattr(self, phase)
            if not method():
                logger.error(f"❌ Pipeline failed at phase: {phase}")
                return False

        return True

    @property
    def data_file(self) -> Path:
        """Path to the data file (can be overridden)."""
        if hasattr(self, "_data_file_override") and self._data_file_override:
            return self._data_file_override
        return self.data_dir / f"{self.symbol}_{self.interval}__{self.days}d.csv"

    @data_file.setter
    def data_file(self, value: Path):
        """Override the data file path."""
        self._data_file_override = value

    # =========================================================================
    # Run Pipeline
    # =========================================================================
    def run(self, phases: list = None) -> bool:
        """Run the full pipeline or specific phases."""
        all_phases = ["download", "collect", "optimize", "validate", "report"]
        phases = phases or all_phases

        logger.info("=" * 60)
        logger.info("🚀 CASINO V3 TRAINING PIPELINE")
        logger.info("=" * 60)
        logger.info(f"   Symbol: {self.symbol}")
        logger.info(f"   Interval: {self.interval}")
        logger.info(f"   Days: {self.days}")
        logger.info(f"   Phases: {', '.join(phases)}")
        logger.info("=" * 60)

        success = self._run_phases(phases)

        if success:
            logger.info("=" * 60)
            logger.info("🎉 PIPELINE COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)

        return success


def main():
    parser = argparse.ArgumentParser(description="Casino V3 Training Pipeline")
    parser.add_argument("--symbol", default="LTCUSDT", help="Trading pair symbol")
    parser.add_argument("--interval", default="1m", help="Candle interval")
    parser.add_argument("--days", type=int, default=30, help="Days of historical data")
    parser.add_argument("--phase", help="Run specific phase only (download, collect, optimize, validate, report)")
    parser.add_argument("--data", help="Use existing data file instead of downloading")
    parser.add_argument("--folder", help="Process all CSV files in folder sequentially (skips download)")

    args = parser.parse_args()

    pipeline = TrainingPipeline(symbol=args.symbol, interval=args.interval, days=args.days)

    # Batch mode: process folder
    if args.folder:
        folder = Path(args.folder)
        if not folder.exists():
            logger.error(f"❌ Folder not found: {folder}")
            return 1
        phases = [args.phase] if args.phase else None
        success = pipeline.run_batch(folder, phases=phases)
        return 0 if success else 1

    # Single file mode
    if args.data:
        pipeline.data_file = Path(args.data)

    # Run specific phase or full pipeline
    phases = [args.phase] if args.phase else None

    success = pipeline.run(phases=phases)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
