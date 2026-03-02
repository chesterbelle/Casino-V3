#!/usr/bin/env python3
"""
Sensor Training Mode

Fast training mode to populate sensor tracker memory by processing
historical data without full backtest overhead.

Usage:
    python utils/train_sensors.py
    python utils/train_sensors.py --files data/raw/LTCUSDT_1m__90d.csv
    python utils/train_sensors.py --tp 0.01 --sl 0.01 --verbose
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config import trading
from decision.sensor_tracker import SensorTracker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SensorTrainer")


class SensorTrainer:
    """Fast training mode for sensor tracker."""

    def __init__(
        self,
        tracker: SensorTracker,
        timeframe: str = "1m",
        tp_pct: float = None,
        sl_pct: float = None,
        max_bars: int = 100,
    ):
        self.tracker = tracker
        self.timeframe = timeframe
        self.tp_pct = tp_pct or trading.TAKE_PROFIT  # Fallback only
        self.sl_pct = sl_pct or trading.STOP_LOSS  # Fallback only
        self.max_bars = max_bars  # Max bars to hold position

        # Load all sensors
        self.sensors = self._load_sensors()

        # Statistics
        self.total_signals = 0
        self.total_trades = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_timeouts = 0

        logger.info(f"✅ SensorTrainer initialized with {len(self.sensors)} sensors")
        logger.info(f"   Timeframe: {self.timeframe} | Using sensor-specific TP/SL from config")

    def _load_sensors(self) -> List:
        """Load Dale/Dalton sensors for pure Order Flow training."""
        # 1. Volume Analysis (Dale)
        from sensors.absorption_block import AbsorptionBlockV3

        # 3. Footprint (Dale/Dalton)
        from sensors.footprint.absorption import FootprintAbsorptionV3
        from sensors.footprint.advanced import (
            FootprintDeltaDivergence,
            FootprintPOCRejection,
            FootprintStackedImbalance,
            FootprintTrappedTraders,
        )
        from sensors.footprint.cumulative_delta import CumulativeDeltaSensorV3
        from sensors.footprint.exhaustion import FootprintVolumeExhaustion
        from sensors.footprint.flow_shift import FootprintDeltaPoCShift
        from sensors.footprint.imbalance import FootprintImbalanceV3

        # 2. Structural Context (Dalton)
        from sensors.regime.one_timeframing import OneTimeframingSensor
        from sensors.volume_imbalance import VolumeImbalanceV3
        from sensors.volume_spike import VolumeSpikeV3
        from sensors.vsa_reversal import VSAReversalV3

        # Instantiate
        sensors = [
            # Volume
            VolumeImbalanceV3(),
            VolumeSpikeV3(),
            VSAReversalV3(),
            AbsorptionBlockV3(),
            # Structural
            OneTimeframingSensor(),
            # Footprint
            FootprintImbalanceV3(),
            FootprintAbsorptionV3(),
            FootprintPOCRejection(),
            FootprintDeltaDivergence(),
            FootprintStackedImbalance(),
            FootprintTrappedTraders(),
            FootprintVolumeExhaustion(),
            FootprintDeltaPoCShift(),
            CumulativeDeltaSensorV3(),
        ]

        return sensors

        return sensors

    def _simulate_trade(self, signal: Dict, entry_idx: int, candles: pd.DataFrame) -> Tuple[Optional[bool], float, int]:
        """
        Simulate a trade based on signal using sensor-specific TP/SL.

        Returns:
            (won: bool or None, pnl: float, bars_held: int)
            won=None means timeout (no TP/SL hit)
        """
        if entry_idx >= len(candles) - 1:
            return None, 0.0, 0  # No future candles

        entry_candle = candles.iloc[entry_idx]
        entry_price = entry_candle["close"]
        side = signal["side"]
        sensor_id = signal.get("sensor_id", "Unknown")

        # Get sensor-specific TP/SL from config
        from config.sensors import get_sensor_params

        sensor_params = get_sensor_params(sensor_id, self.timeframe)
        tp_pct = sensor_params.get("tp_pct", self.tp_pct)
        sl_pct = sensor_params.get("sl_pct", self.sl_pct)

        # Calculate TP/SL prices
        if side == "LONG":
            tp_price = entry_price * (1 + tp_pct)
            sl_price = entry_price * (1 - sl_pct)
        else:  # SHORT
            tp_price = entry_price * (1 - tp_pct)
            sl_price = entry_price * (1 + sl_pct)

        # Scan forward candles
        max_idx = min(entry_idx + self.max_bars, len(candles))
        for i in range(entry_idx + 1, max_idx):
            candle = candles.iloc[i]
            bars_held = i - entry_idx

            if side == "LONG":
                # Check TP hit
                if candle["high"] >= tp_price:
                    return True, tp_pct - 0.0012, bars_held  # Deduct 0.12% fees
                # Check SL hit
                if candle["low"] <= sl_price:
                    return False, -sl_pct - 0.0012, bars_held  # Deduct 0.12% fees
            else:  # SHORT
                # Check TP hit
                if candle["low"] <= tp_price:
                    return True, tp_pct - 0.0012, bars_held  # Deduct 0.12% fees
                # Check SL hit
                if candle["high"] >= sl_price:
                    return False, -sl_pct - 0.0012, bars_held  # Deduct 0.12% fees

        # Timeout - no TP/SL hit
        return None, 0.0, max_idx - entry_idx

    def train_on_file(self, csv_file: Path, verbose: bool = False) -> Dict:
        """
        Train on a single CSV file.

        Args:
            csv_file: Path to CSV file
            verbose: Print detailed progress

        Returns:
            Statistics dict
        """
        logger.info(f"📂 Processing: {csv_file.name}")

        # Load candles
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            logger.error(f"❌ Failed to load {csv_file}: {e}")
            return {}

        # Validate columns
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required_cols):
            logger.error(f"❌ Missing required columns in {csv_file}")
            return {}

        logger.info(f"   Loaded {len(df)} candles")

        # Statistics for this file
        file_signals = 0
        file_trades = 0
        file_wins = 0
        file_losses = 0
        file_timeouts = 0

        # Process each candle
        for idx, row in df.iterrows():
            candle_dict = {
                "timestamp": row["timestamp"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }

            # Run all sensors on this candle
            for sensor in self.sensors:
                try:
                    signal = sensor.calculate(candle_dict)

                    if signal:
                        file_signals += 1
                        self.total_signals += 1

                        # Simulate outcome
                        won, pnl, bars_held = self._simulate_trade(signal, idx, df)

                        if won is not None:
                            # Valid trade (TP or SL hit)
                            file_trades += 1
                            self.total_trades += 1

                            if won:
                                file_wins += 1
                                self.total_wins += 1
                            else:
                                file_losses += 1
                                self.total_losses += 1

                            # Update tracker
                            self.tracker.update_sensor(sensor.name, pnl, won)

                            if verbose and file_trades % 100 == 0:
                                logger.debug(
                                    f"   {sensor.name}: {signal['side']} → "
                                    f"{'WIN' if won else 'LOSS'} | "
                                    f"PnL: {pnl:+.2%} | Bars: {bars_held}"
                                )
                        else:
                            # Timeout
                            file_timeouts += 1
                            self.total_timeouts += 1

                except Exception as e:
                    if verbose:
                        logger.error(f"   Error in {sensor.name}: {e}")

            # Progress update every 1000 candles
            if verbose and idx % 1000 == 0 and idx > 0:
                logger.info(
                    f"   Progress: {idx}/{len(df)} candles | " f"Signals: {file_signals} | Trades: {file_trades}"
                )

        # File summary
        win_rate = (file_wins / file_trades * 100) if file_trades > 0 else 0
        logger.info(
            f"   ✅ Signals: {file_signals} | Trades: {file_trades} | "
            f"WR: {win_rate:.1f}% | Timeouts: {file_timeouts}"
        )

        return {
            "signals": file_signals,
            "trades": file_trades,
            "wins": file_wins,
            "losses": file_losses,
            "timeouts": file_timeouts,
            "win_rate": win_rate,
        }

    def train_all(self, data_dir: Path, file_pattern: str = "*.csv", verbose: bool = False):
        """
        Train on all CSV files in directory.

        Args:
            data_dir: Directory containing CSV files
            file_pattern: Glob pattern for files
            verbose: Print detailed progress
        """
        csv_files = sorted(data_dir.glob(file_pattern))

        if not csv_files:
            logger.warning(f"⚠️  No CSV files found in {data_dir}")
            return

        logger.info(f"🚀 Starting training on {len(csv_files)} files")
        logger.info("=" * 80)

        start_time = time.time()

        for csv_file in csv_files:
            self.train_on_file(csv_file, verbose=verbose)

        elapsed = time.time() - start_time

        # Final summary
        logger.info("=" * 80)
        logger.info("📊 TRAINING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Files Processed:      {len(csv_files)}")
        logger.info(f"Total Signals:        {self.total_signals}")
        logger.info(f"Total Trades:         {self.total_trades}")
        logger.info(f"Wins / Losses:        {self.total_wins} / {self.total_losses}")

        if self.total_trades > 0:
            overall_wr = self.total_wins / self.total_trades * 100
            logger.info(f"Overall Win Rate:     {overall_wr:.2f}%")

        logger.info(f"Timeouts:             {self.total_timeouts}")
        logger.info(f"Time Elapsed:         {elapsed:.1f}s")
        logger.info("=" * 80)

        # Save tracker state
        self.tracker.save_state()
        logger.info(f"💾 Tracker state saved to {self.tracker.state_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Train sensor tracker on historical data")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory containing CSV files",
    )
    parser.add_argument(
        "--files",
        type=str,
        help="Specific CSV file(s) to process (comma-separated)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default=None,
        help="Timeframe (1m, 5m, 15m). Auto-detected from filename if not specified.",
    )
    parser.add_argument("--tp", type=float, help="Take profit percentage (default: from config)")
    parser.add_argument("--sl", type=float, help="Stop loss percentage (default: from config)")
    parser.add_argument(
        "--max-bars",
        type=int,
        default=100,
        help="Maximum bars to hold position (default: 100)",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Auto-detect timeframe from first filename if not specified
    if args.timeframe is None and args.files:
        import re

        first_file = args.files.split(",")[0].strip()
        match = re.search(r"_(\d+[mh])_", first_file)
        timeframe = match.group(1) if match else "1m"
        logger.info(f"📊 Auto-detected timeframe: {timeframe}")
    else:
        timeframe = args.timeframe or "1m"
        logger.info(f"📊 Using timeframe: {timeframe}")

    # Initialize tracker
    tracker = SensorTracker()

    # Initialize trainer
    trainer = SensorTrainer(
        tracker=tracker,
        timeframe=timeframe,
        tp_pct=args.tp,
        sl_pct=args.sl,
        max_bars=args.max_bars,
    )

    # Train on specific files or all files
    if args.files:
        file_paths = [Path(f.strip()) for f in args.files.split(",")]
        for file_path in file_paths:
            if file_path.exists():
                trainer.train_on_file(file_path, verbose=args.verbose)
            else:
                logger.error(f"❌ File not found: {file_path}")
    else:
        trainer.train_all(args.data_dir, verbose=args.verbose)

    # Save stats to disk
    tracker.save_state()
    logger.info(f"💾 Sensor stats saved to state/sensor_stats.json")


if __name__ == "__main__":
    main()
