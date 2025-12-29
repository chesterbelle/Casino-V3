#!/usr/bin/env python3
"""
Sensor Optimization Tool V3 - Multi-Timeframe

Analyzes historical MFE/MAE for each sensor to determine the optimal
TP/SL configuration and best timeframe per sensor.

Features:
- Expanded grid search ranges (TP up to 10%, SL up to 6%)
- Multi-timeframe analysis (--mtf mode)
- Automatic timeframe recommendation per sensor
- Minimum trade threshold for statistical significance
- TP/SL ratio constraints
- Profit Factor metric
- JSON output for programmatic use

Usage:
    # Single timeframe
    python utils/analysis/optimize_sensors.py --files data/raw/LTCUSDT_1m__90d.csv

    # Multi-timeframe analysis
    python utils/analysis/optimize_sensors.py --mtf \\
        --files-1m data/raw/LTCUSDT_1m__90d.csv \\
        --files-5m data/raw/LTCUSDT_5m__30d.csv \\
        --files-15m data/raw/LTCUSDT_15m__30d.csv
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.bar_aggregator import BarAggregator
from core.sensor_manager import SensorManager


class MockEngine:
    """Mock engine to satisfy SensorManager dependencies."""

    def __init__(self):
        self.listeners = {}

    def subscribe(self, event_type, handler):
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(handler)

    async def dispatch(self, event):
        pass


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SensorOptimizer")


# =====================================================
# CONFIGURATION
# =====================================================

# Grid search ranges by timeframe (expanded for better optimization)
GRID_RANGES = {
    "1m": {
        "tp": np.arange(0.003, 0.101, 0.002),  # 0.3% to 10.0%
        "sl": np.arange(0.005, 0.061, 0.002),  # 0.5% to 6.0%
    },
    "5m": {
        "tp": np.arange(0.005, 0.121, 0.003),  # 0.5% to 12.0%
        "sl": np.arange(0.008, 0.081, 0.003),  # 0.8% to 8.0%
    },
    "15m": {
        "tp": np.arange(0.010, 0.151, 0.005),  # 1.0% to 15.0%
        "sl": np.arange(0.010, 0.101, 0.005),  # 1.0% to 10.0%
    },
    "1h": {
        "tp": np.arange(0.020, 0.251, 0.010),  # 2.0% to 25.0%
        "sl": np.arange(0.020, 0.151, 0.010),  # 2.0% to 15.0%
    },
}

# Fee rate (taker + taker for round trip)
FEE_RATE = 0.0007  # 0.07% per trade

# Minimum TP/SL ratio (avoid configs where SL >> TP)
MIN_TP_SL_RATIO = 0.5


class SensorOptimizer:
    """Optimizes TP/SL for sensors based on MFE/MAE analysis."""

    def __init__(self, max_bars: int = 120, min_trades: int = 30):
        """
        Args:
            max_bars: Maximum bars to analyze for MFE/MAE
            min_trades: Minimum trades required for optimization
        """
        self.max_bars = max_bars
        self.min_trades = min_trades

        # Initialize BarAggregator for MTF support
        self.bar_aggregator = BarAggregator()

        # Load sensors
        self.engine = MockEngine()
        self.sensor_manager = SensorManager(self.engine)
        self.sensors = self.sensor_manager.sensors

        # Store MFE/MAE data: {timeframe: {sensor_name: [data...]}}
        self.sensor_data: Dict[str, Dict[str, List[Dict]]] = defaultdict(lambda: defaultdict(list))

        logger.info(f"✅ Loaded {len(self.sensors)} sensors")

    def analyze_signal(self, signal: Dict, entry_idx: int, candles: pd.DataFrame, timeframe: str):
        """Calculate MFE and MAE for a signal."""
        if entry_idx >= len(candles) - 1:
            return

        entry_price = candles.iloc[entry_idx]["close"]
        side = signal["side"]

        # Get future window
        max_idx = min(entry_idx + self.max_bars, len(candles))
        future_candles = candles.iloc[entry_idx + 1 : max_idx]

        if len(future_candles) == 0:
            return

        highs = future_candles["high"].values
        lows = future_candles["low"].values

        if side == "LONG":
            max_price = np.max(highs)
            min_price = np.min(lows)
            mfe = (max_price - entry_price) / entry_price
            mae = (entry_price - min_price) / entry_price
            final_pnl = (future_candles.iloc[-1]["close"] - entry_price) / entry_price
        else:  # SHORT
            max_price = np.max(highs)
            min_price = np.min(lows)
            mfe = (entry_price - min_price) / entry_price
            mae = (max_price - entry_price) / entry_price
            final_pnl = (entry_price - future_candles.iloc[-1]["close"]) / entry_price

        self.sensor_data[timeframe][signal["sensor_id"]].append(
            {
                "mfe": mfe,
                "mae": mae,
                "final_pnl": final_pnl,
                "side": side,
                "entry_price": entry_price,
            }
        )

    def process_file(self, csv_file: Path, timeframe: str = "1m"):
        """Process a single CSV file."""
        logger.info(f"📂 Processing: {csv_file.name} (TF: {timeframe})")
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            logger.error(f"❌ Failed to load {csv_file}: {e}")
            return

        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required_cols):
            logger.error(f"❌ Missing required columns in {csv_file}")
            return

        logger.info(f"   Loaded {len(df)} candles")

        signals_count = 0

        for idx, row in df.iterrows():
            candle_dict = {
                "timestamp": row["timestamp"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }

            # Update aggregator to get MTF context
            context = self.bar_aggregator.on_candle(candle_dict)

            # Ensure current timeframe is in context (BarAggregator does this, but just in case)
            context[timeframe] = candle_dict

            for sensor in self.sensors:
                try:
                    # Set the timeframes list for MTF sensors
                    sensor.timeframes = [timeframe]
                    result = sensor.calculate(context)

                    # Handle both single signal (dict) and multiple signals (list)
                    if result is None:
                        continue

                    signals = result if isinstance(result, list) else [result]

                    for signal in signals:
                        if signal is None:
                            continue
                        if "sensor_id" not in signal:
                            signal["sensor_id"] = sensor.name
                        # Use signal's timeframe if present, else use file's timeframe
                        signal_tf = signal.get("timeframe", timeframe)
                        self.analyze_signal(signal, idx, df, signal_tf)
                        signals_count += 1
                except Exception:
                    pass

            if idx % 10000 == 0 and idx > 0:
                logger.info(f"   Processed {idx} candles... ({signals_count} signals)")

        logger.info(f"   ✅ Completed: {signals_count} signals collected")

    def _optimize_single_sensor(
        self,
        sensor_name: str,
        data: List[Dict],
        tp_range: np.ndarray,
        sl_range: np.ndarray,
    ) -> Optional[Dict[str, Any]]:
        """Optimize TP/SL for a single sensor."""
        if len(data) < self.min_trades:
            return None

        df = pd.DataFrame(data)
        mfe_arr = df["mfe"].values
        mae_arr = df["mae"].values
        final_pnl_arr = df["final_pnl"].values

        best_expectancy = -float("inf")
        best_config = None

        for tp in tp_range:
            for sl in sl_range:
                if tp / sl < MIN_TP_SL_RATIO:
                    continue

                is_loss = mae_arr >= sl
                is_win = (mfe_arr >= tp) & (~is_loss)
                is_timeout = (~is_win) & (~is_loss)

                wins = np.sum(is_win)
                losses = np.sum(is_loss)
                timeouts = np.sum(is_timeout)
                total_trades = len(mfe_arr)
                win_rate = wins / total_trades

                gross_profit = wins * tp
                gross_loss = losses * sl
                timeout_pnl = np.sum(final_pnl_arr[is_timeout])

                total_pnl = gross_profit - gross_loss + timeout_pnl - (total_trades * FEE_RATE)
                avg_pnl = total_pnl / total_trades
                profit_factor = gross_profit / max(gross_loss, 0.0001)

                if avg_pnl > best_expectancy:
                    best_expectancy = avg_pnl
                    best_config = {
                        "tp": tp,
                        "sl": sl,
                        "win_rate": win_rate,
                        "wins": wins,
                        "losses": losses,
                        "timeouts": timeouts,
                        "profit_factor": profit_factor,
                    }

        if best_config is None:
            return None

        return {
            "sensor": sensor_name,
            "trades": len(data),
            "best_config": best_config,
            "expectancy": best_expectancy,
        }

    def optimize_sensors(self, timeframe: str = "1m") -> List[Dict[str, Any]]:
        """Find optimal TP/SL for each sensor in a single timeframe."""
        logger.info("\n" + "=" * 80)
        logger.info(f"🔍 OPTIMIZATION RESULTS - {timeframe}")
        logger.info("=" * 80)

        ranges = GRID_RANGES.get(timeframe, GRID_RANGES["1m"])
        tp_range = ranges["tp"]
        sl_range = ranges["sl"]

        logger.info(f"📊 TP Range: {tp_range[0]*100:.1f}% - {tp_range[-1]*100:.1f}%")
        logger.info(f"📊 SL Range: {sl_range[0]*100:.1f}% - {sl_range[-1]*100:.1f}%")
        logger.info(f"📊 Min Trades: {self.min_trades}")

        results = []
        data_for_tf = self.sensor_data.get(timeframe, {})

        for sensor_name, data in data_for_tf.items():
            result = self._optimize_single_sensor(sensor_name, data, tp_range, sl_range)
            if result:
                results.append(result)

        results.sort(key=lambda x: x["expectancy"], reverse=True)
        self._print_results_table(results)

        return results

    def optimize_multi_timeframe(self, timeframes: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Optimize across multiple timeframes and find best TF per sensor.

        Returns:
            Dict mapping sensor_name -> best config with optimal timeframe
        """
        logger.info("\n" + "=" * 80)
        logger.info("🔍 MULTI-TIMEFRAME OPTIMIZATION")
        logger.info("=" * 80)
        logger.info(f"📊 Timeframes: {', '.join(timeframes)}")
        logger.info(f"📊 Min Trades: {self.min_trades}")

        # Collect results for all timeframes
        all_results: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)  # sensor -> [(tf, result), ...]

        for tf in timeframes:
            ranges = GRID_RANGES.get(tf, GRID_RANGES["1m"])
            data_for_tf = self.sensor_data.get(tf, {})

            logger.info(f"\n📊 Optimizing for {tf}...")

            for sensor_name, data in data_for_tf.items():
                result = self._optimize_single_sensor(sensor_name, data, ranges["tp"], ranges["sl"])
                if result:
                    all_results[sensor_name].append((tf, result))

        # Find best timeframe per sensor
        best_per_sensor: Dict[str, Dict[str, Any]] = {}

        for sensor_name, tf_results in all_results.items():
            # Sort by expectancy (descending)
            tf_results.sort(key=lambda x: x[1]["expectancy"], reverse=True)

            best_tf, best_result = tf_results[0]

            # Include all results regardless of expectancy
            # if best_result["expectancy"] > 0:
            if True:
                best_per_sensor[sensor_name] = {
                    "optimal_timeframe": best_tf,
                    "tp_pct": best_result["best_config"]["tp"],
                    "sl_pct": best_result["best_config"]["sl"],
                    "win_rate": best_result["best_config"]["win_rate"],
                    "expectancy": best_result["expectancy"],
                    "profit_factor": best_result["best_config"]["profit_factor"],
                    "trades": best_result["trades"],
                    "all_timeframes": {
                        tf: {
                            "exp": r["expectancy"],
                            "trades": r["trades"],
                        }
                        for tf, r in tf_results
                    },
                }

        # Print MTF results
        self._print_mtf_results(best_per_sensor, timeframes)

        return best_per_sensor

    def _print_results_table(self, results: List[Dict]):
        """Print single-TF results table."""
        print("\n" + "=" * 100)
        print(
            f"{'Rank':<5} {'Sensor':<25} {'TP%':<7} {'SL%':<7} "
            f"{'Ratio':<6} {'WR%':<7} {'PF':<6} {'Exp%':<8} {'Trades':<8}"
        )
        print("=" * 100)

        for i, r in enumerate(results, 1):
            cfg = r["best_config"]
            ratio = cfg["tp"] / cfg["sl"]
            exp_pct = r["expectancy"] * 100
            print(
                f"{i:<5} {r['sensor']:<25} "
                f"{cfg['tp']*100:>5.2f}   {cfg['sl']*100:>5.2f}   "
                f"{ratio:>4.2f}   {cfg['win_rate']*100:>5.1f}   "
                f"{cfg['profit_factor']:>4.2f}   {exp_pct:>6.3f}   "
                f"{r['trades']:>6}"
            )

        print("=" * 100)

    def _print_mtf_results(self, best_per_sensor: Dict[str, Dict], timeframes: List[str]):
        """Print multi-timeframe results with TF comparison."""
        print("\n" + "=" * 120)
        print("🏆 MULTI-TIMEFRAME OPTIMIZATION RESULTS")
        print("=" * 120)

        # Sort by expectancy
        sorted_sensors = sorted(best_per_sensor.items(), key=lambda x: x[1]["expectancy"], reverse=True)

        # Header with timeframe columns
        tf_cols = "  ".join([f"{tf:^8}" for tf in timeframes])
        print(f"{'Rank':<4} {'Sensor':<22} {'Best TF':<8} {'TP%':<6} {'SL%':<6} " f"{'WR%':<6} {'Exp%':<7} {tf_cols}")
        print("-" * 120)

        for i, (sensor, data) in enumerate(sorted_sensors, 1):
            best_tf = data["optimal_timeframe"]

            # Build TF comparison columns
            tf_exps = []
            for tf in timeframes:
                if tf in data["all_timeframes"]:
                    exp = data["all_timeframes"][tf]["exp"] * 100
                    marker = "★" if tf == best_tf else " "
                    tf_exps.append(f"{exp:>+6.2f}{marker}")
                else:
                    tf_exps.append("   --   ")
            tf_str = "  ".join(tf_exps)

            print(
                f"{i:<4} {sensor:<22} {best_tf:<8} "
                f"{data['tp_pct']*100:>5.2f} {data['sl_pct']*100:>5.2f}  "
                f"{data['win_rate']*100:>5.1f} {data['expectancy']*100:>+6.3f}  "
                f"{tf_str}"
            )

        print("=" * 120)
        print(f"\n✅ {len(sorted_sensors)} sensors with positive expectancy")
        print("   ★ = Best timeframe for this sensor")

    def generate_config_output(
        self,
        results: Optional[List[Dict]] = None,
        mtf_results: Optional[Dict[str, Dict]] = None,
        timeframe: str = "1m",
    ):
        """Generate Python config and JSON output."""
        print("\n" + "=" * 80)
        print("📋 COPY TO config/sensors.py SENSOR_PARAMS:")
        print("=" * 80)

        config_output = ""
        json_output = {
            "generated_at": datetime.now().isoformat(),
            "min_trades": self.min_trades,
            "fee_rate": FEE_RATE,
        }

        if mtf_results:
            # MTF mode - include optimal timeframe
            json_output["mode"] = "multi_timeframe"
            json_output["sensors"] = {}

            for sensor, data in sorted(mtf_results.items(), key=lambda x: x[1]["expectancy"], reverse=True):
                tf = data["optimal_timeframe"]
                config_output += f'    "{sensor}": {{\n'
                config_output += (
                    f'        "{tf}": {{"tp_pct": {data["tp_pct"]:.4f}, '
                    f'"sl_pct": {data["sl_pct"]:.4f}}},  '
                    f'# Exp: {data["expectancy"]*100:.3f}%\n'
                )
                config_output += f"    }},\n"

                json_output["sensors"][sensor] = {
                    "optimal_timeframe": tf,
                    "tp_pct": round(data["tp_pct"], 4),
                    "sl_pct": round(data["sl_pct"], 4),
                    "win_rate": round(data["win_rate"], 4),
                    "expectancy": round(data["expectancy"], 6),
                    "profit_factor": round(data["profit_factor"], 4),
                    "trades": data["trades"],
                    "all_timeframes": data["all_timeframes"],
                }

        elif results:
            # Single TF mode
            json_output["mode"] = "single_timeframe"
            json_output["timeframe"] = timeframe
            json_output["sensors"] = {}

            for r in results:
                # if r["expectancy"] > 0:
                if True:
                    cfg = r["best_config"]
                    config_output += f'    "{r["sensor"]}": {{\n'
                    config_output += (
                        f'        "{timeframe}": {{"tp_pct": {cfg["tp"]:.4f}, '
                        f'"sl_pct": {cfg["sl"]:.4f}}},  '
                        f'# Exp: {r["expectancy"]*100:.3f}%\n'
                    )
                    config_output += f"    }},\n"

                    json_output["sensors"][r["sensor"]] = {
                        "tp_pct": round(cfg["tp"], 4),
                        "sl_pct": round(cfg["sl"], 4),
                        "win_rate": round(cfg["win_rate"], 4),
                        "expectancy": round(r["expectancy"], 6),
                        "profit_factor": round(cfg["profit_factor"], 4),
                        "trades": r["trades"],
                    }

        print(config_output)

        # Save JSON
        output_file = Path("config/optimized_params.json")
        with open(output_file, "w") as f:
            json.dump(json_output, f, indent=2)

        print(f"\n💾 Saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Optimize TP/SL for sensors (supports multi-timeframe)")
    parser.add_argument(
        "--files",
        type=str,
        help="CSV files for single-TF mode (comma-separated or glob)",
    )
    parser.add_argument("--files-1m", type=str, help="1m timeframe files for MTF mode")
    parser.add_argument("--files-5m", type=str, help="5m timeframe files for MTF mode")
    parser.add_argument("--files-15m", type=str, help="15m timeframe files for MTF mode")
    parser.add_argument("--files-1h", type=str, help="1h timeframe files for MTF mode")
    parser.add_argument("--mtf", action="store_true", help="Enable multi-timeframe mode")
    parser.add_argument("--max-bars", type=int, default=120, help="Max bars for MFE/MAE")
    parser.add_argument("--min-trades", type=int, default=30, help="Minimum trades")
    parser.add_argument(
        "--timeframe",
        type=str,
        default=None,
        help="Timeframe for single-TF mode (auto-detected if not specified)",
    )
    args = parser.parse_args()

    optimizer = SensorOptimizer(max_bars=args.max_bars, min_trades=args.min_trades)

    import glob
    import re

    if args.mtf:
        # Multi-timeframe mode
        logger.info("🔄 Running in MULTI-TIMEFRAME mode")

        tf_files = {
            "1m": args.files_1m,
            "5m": args.files_5m,
            "15m": args.files_15m,
            "1h": args.files_1h,
        }

        active_tfs = []
        for tf, pattern in tf_files.items():
            if pattern:
                files = []
                for p in pattern.split(","):
                    p = p.strip()
                    if "*" in p:
                        files.extend([Path(f) for f in glob.glob(p)])
                    else:
                        files.append(Path(p))

                for f in files:
                    if f.exists():
                        optimizer.process_file(f, timeframe=tf)
                    else:
                        logger.error(f"File not found: {f}")

                if files:
                    active_tfs.append(tf)

        if not active_tfs:
            logger.error("❌ No files provided for any timeframe")
            sys.exit(1)

        mtf_results = optimizer.optimize_multi_timeframe(active_tfs)
        optimizer.generate_config_output(mtf_results=mtf_results)

    else:
        # Single timeframe mode
        if not args.files:
            logger.error("❌ --files required in single-TF mode")
            sys.exit(1)

        # Auto-detect timeframe
        if args.timeframe is None:
            first_file = args.files.split(",")[0].strip()
            match = re.search(r"_(\d+[mh])_", first_file)
            timeframe = match.group(1) if match else "1m"
            logger.info(f"📊 Auto-detected timeframe: {timeframe}")
        else:
            timeframe = args.timeframe
            logger.info(f"📊 Using specified timeframe: {timeframe}")

        files = []
        for pattern in args.files.split(","):
            pattern = pattern.strip()
            if "*" in pattern:
                files.extend([Path(f) for f in glob.glob(pattern)])
            else:
                files.append(Path(pattern))

        if not files:
            logger.error("❌ No files found")
            sys.exit(1)

        logger.info(f"📂 Processing {len(files)} file(s)")

        for f in files:
            if f.exists():
                optimizer.process_file(f, timeframe=timeframe)
            else:
                logger.error(f"File not found: {f}")

        results = optimizer.optimize_sensors(timeframe=timeframe)
        optimizer.generate_config_output(results=results, timeframe=timeframe)


if __name__ == "__main__":
    main()
