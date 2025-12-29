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
        """Load all V3 sensors."""
        # Import all sensors
        from sensors.absorption_block import AbsorptionBlockV3
        from sensors.adaptive_rsi import AdaptiveRSIV3
        from sensors.adx_filter import ADXFilterV3
        from sensors.bollinger_rejection import BollingerRejectionV3
        from sensors.bollinger_squeeze import BollingerSqueezeV3
        from sensors.bollinger_touch import BollingerTouchV3
        from sensors.cci_reversion import CCIReversionV3
        from sensors.deceleration_candles import DecelerationCandlesV3
        from sensors.doji_indecision import DojiIndecisionV3
        from sensors.ema50_support import EMA50SupportV3
        from sensors.ema_crossover import EMACrossoverV3
        from sensors.engulfing_pattern import EngulfingPatternV3
        from sensors.extreme_candle_ratio import ExtremeCandleRatioV3
        from sensors.fakeout import FakeoutV3
        from sensors.fvg_retest import FVGRetestV3
        from sensors.higher_tf_trend import HigherTFTrendV3
        from sensors.hurst_regime import HurstRegimeV3
        from sensors.inside_bar_breakout import InsideBarBreakoutV3
        from sensors.keltner_breakout import KeltnerBreakoutV3
        from sensors.keltner_reversion import KeltnerReversionV3
        from sensors.liquidity_void import LiquidityVoidV3
        from sensors.long_tail import LongTailV3
        from sensors.macd_crossover import MACDCrossoverV3
        from sensors.marubozu_momentum import MarubozuMomentumV3
        from sensors.micro_trend import MicroTrendV3
        from sensors.momentum_burst import MomentumBurstV3
        from sensors.morning_star import MorningStarV3
        from sensors.mtf_impulse import MTFImpulseV3
        from sensors.order_block import OrderBlockV3
        from sensors.parabolic_sar import ParabolicSARV3
        from sensors.pinbar_reversal import PinBarReversalV3
        from sensors.rails_pattern import RailsPatternV3
        from sensors.rsi_reversion import RSIReversionV3
        from sensors.smart_range import SmartRangeV3
        from sensors.stochastic_reversion import StochasticReversionV3
        from sensors.supertrend import SupertrendV3
        from sensors.support_resistance import SupportResistanceV3
        from sensors.three_bar import ThreeBarV3
        from sensors.tweezer_pattern import TweezerPatternV3
        from sensors.vcp_pattern import VCPPatternV3
        from sensors.volatility_wakeup import VolatilityWakeupV3
        from sensors.volume_imbalance import VolumeImbalanceV3
        from sensors.volume_spike import VolumeSpikeV3
        from sensors.vsa_reversal import VSAReversalV3
        from sensors.vwap_breakout import VWAPBreakoutV3
        from sensors.vwap_deviation import VWAPDeviationV3
        from sensors.vwap_momentum import VWAPMomentumV3
        from sensors.wick_rejection import WickRejectionV3
        from sensors.williams_r_reversion import WilliamsRReversionV3
        from sensors.wyckoff_spring import WyckoffSpringV3
        from sensors.zscore_reversion import ZScoreReversionV3

        # Instantiate all sensors
        sensors = [
            EMACrossoverV3(),
            PinBarReversalV3(),
            RailsPatternV3(),
            EMA50SupportV3(),
            MarubozuMomentumV3(),
            VWAPBreakoutV3(),
            ExtremeCandleRatioV3(),
            InsideBarBreakoutV3(),
            DecelerationCandlesV3(),
            VWAPDeviationV3(),
            VCPPatternV3(),
            EngulfingPatternV3(),
            RSIReversionV3(),
            BollingerTouchV3(),
            KeltnerReversionV3(),
            MACDCrossoverV3(),
            SupertrendV3(),
            StochasticReversionV3(),
            CCIReversionV3(),
            WilliamsRReversionV3(),
            ZScoreReversionV3(),
            ADXFilterV3(),
            BollingerSqueezeV3(),
            ParabolicSARV3(),
            MomentumBurstV3(),
            VolumeImbalanceV3(),
            OrderBlockV3(),
            FVGRetestV3(),
            DojiIndecisionV3(),
            MorningStarV3(),
            LongTailV3(),
            AbsorptionBlockV3(),
            LiquidityVoidV3(),
            FakeoutV3(),
            HigherTFTrendV3(),
            MTFImpulseV3(),
            AdaptiveRSIV3(),
            BollingerRejectionV3(),
            HurstRegimeV3(),
            KeltnerBreakoutV3(),
            MicroTrendV3(),
            SmartRangeV3(),
            VolatilityWakeupV3(),
            VSAReversalV3(),
            VWAPMomentumV3(),
            WickRejectionV3(),
            WyckoffSpringV3(),
            VolumeSpikeV3(),
            TweezerPatternV3(),
            ThreeBarV3(),
            SupportResistanceV3(),
        ]

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
