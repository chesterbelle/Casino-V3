#!/usr/bin/env python3
"""
Sensor Tracker Analysis Utility

Analyzes the sensor tracker memory (sensor_stats.json) to provide insights
for sensor implementation and improvement.

Usage:
    python utils/sensor_analysis.py
    python utils/sensor_analysis.py --top 20
    python utils/sensor_analysis.py --detailed
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


class SensorAnalyzer:
    """Analyzes sensor performance from tracker memory."""

    def __init__(self, stats_file: Path = Path("state/sensor_stats.json")):
        self.stats_file = stats_file
        self.sensors = {}
        self._load_stats()

    def _load_stats(self):
        """Load sensor statistics from JSON file."""
        if not self.stats_file.exists():
            print(f"❌ Stats file not found: {self.stats_file}")
            print("💡 Run a backtest first to generate sensor stats.")
            return

        with open(self.stats_file, "r") as f:
            self.sensors = json.load(f)

        print(f"✅ Loaded stats for {len(self.sensors)} sensors\n")

    def calculate_score(self, stats: Dict) -> float:
        """Calculate composite score (same formula as SensorTracker)."""
        if stats["total_trades"] < 10:
            return 0.5  # Neutral for insufficient data

        # Normalize components
        expectancy_norm = min(max(stats["expectancy"] / 0.05, 0.0), 1.0)
        win_rate_norm = stats["win_rate_short"]
        profit_factor_norm = min(stats["profit_factor"] / 3.0, 1.0)

        # Streak bonus
        streak = stats["current_streak"]
        if streak > 0:
            streak_bonus = min(streak / 5.0, 1.0)
        else:
            streak_bonus = max(streak / 5.0, -1.0)

        # Composite score
        score = (
            expectancy_norm * 0.4 + win_rate_norm * 0.3 + profit_factor_norm * 0.2 + (streak_bonus * 0.5 + 0.5) * 0.1
        )

        return max(min(score, 1.0), 0.0)

    def get_ranked_sensors(self) -> List[Tuple[str, float, Dict]]:
        """Get sensors ranked by score."""
        ranked = []
        for sensor_id, stats in self.sensors.items():
            score = self.calculate_score(stats)
            ranked.append((sensor_id, score, stats))

        return sorted(ranked, key=lambda x: x[1], reverse=True)

    def print_summary(self):
        """Print overall summary statistics."""
        if not self.sensors:
            return

        total_sensors = len(self.sensors)
        total_trades = sum(s["total_trades"] for s in self.sensors.values())
        active_sensors = sum(1 for s in self.sensors.values() if s["total_trades"] >= 10)

        avg_win_rate = (
            sum(s["win_rate_short"] for s in self.sensors.values()) / total_sensors if total_sensors > 0 else 0
        )

        print("=" * 80)
        print("📊 SENSOR TRACKER ANALYSIS")
        print("=" * 80)
        print(f"Total Sensors:        {total_sensors}")
        print(f"Active Sensors:       {active_sensors} (≥10 trades)")
        print(f"Total Trades:         {total_trades}")
        print(f"Avg Win Rate:         {avg_win_rate:.1%}")
        print("=" * 80)
        print()

    def print_top_sensors(self, n: int = 10):
        """Print top N sensors by score."""
        ranked = self.get_ranked_sensors()

        print(f"🏆 TOP {n} SENSORS BY SCORE")
        print("-" * 80)
        print(f"{'Rank':<6} {'Sensor':<30} {'Score':<8} {'WR':<8} {'Exp':<10} {'PF':<8} {'Trades':<8}")
        print("-" * 80)

        for i, (sensor_id, score, stats) in enumerate(ranked[:n], 1):
            print(
                f"{i:<6} {sensor_id:<30} {score:.3f}    "
                f"{stats['win_rate_short']:.1%}    "
                f"{stats['expectancy']:+.4f}    "
                f"{stats['profit_factor']:.2f}    "
                f"{stats['total_trades']:<8}"
            )

        print()

    def print_bottom_sensors(self, n: int = 10):
        """Print bottom N sensors by score."""
        ranked = self.get_ranked_sensors()

        print(f"⚠️  BOTTOM {n} SENSORS BY SCORE")
        print("-" * 80)
        print(f"{'Rank':<6} {'Sensor':<30} {'Score':<8} {'WR':<8} {'Exp':<10} {'PF':<8} {'Trades':<8}")
        print("-" * 80)

        for i, (sensor_id, score, stats) in enumerate(reversed(ranked[-n:]), 1):
            print(
                f"{i:<6} {sensor_id:<30} {score:.3f}    "
                f"{stats['win_rate_short']:.1%}    "
                f"{stats['expectancy']:+.4f}    "
                f"{stats['profit_factor']:.2f}    "
                f"{stats['total_trades']:<8}"
            )

        print()

    def print_detailed_analysis(self):
        """Print detailed analysis with insights."""
        ranked = self.get_ranked_sensors()

        # Category analysis
        excellent = [s for s in ranked if s[1] >= 0.7]
        good = [s for s in ranked if 0.6 <= s[1] < 0.7]
        neutral = [s for s in ranked if 0.4 <= s[1] < 0.6]
        poor = [s for s in ranked if 0.3 <= s[1] < 0.4]
        terrible = [s for s in ranked if s[1] < 0.3]

        print("📈 PERFORMANCE DISTRIBUTION")
        print("-" * 80)
        print(f"Excellent (≥0.7):     {len(excellent):<4} sensors")
        print(f"Good (0.6-0.7):       {len(good):<4} sensors")
        print(f"Neutral (0.4-0.6):    {len(neutral):<4} sensors")
        print(f"Poor (0.3-0.4):       {len(poor):<4} sensors")
        print(f"Terrible (<0.3):      {len(terrible):<4} sensors")
        print()

        # Expectancy analysis
        positive_exp = [s for s in ranked if s[2]["expectancy"] > 0]
        negative_exp = [s for s in ranked if s[2]["expectancy"] < 0]

        print("💰 EXPECTANCY ANALYSIS")
        print("-" * 80)
        print(f"Positive Expectancy:  {len(positive_exp):<4} sensors")
        print(f"Negative Expectancy:  {len(negative_exp):<4} sensors")

        if positive_exp:
            best_exp = max(positive_exp, key=lambda x: x[2]["expectancy"])
            print(f"Best Expectancy:      {best_exp[0]} ({best_exp[2]['expectancy']:+.4f})")

        if negative_exp:
            worst_exp = min(negative_exp, key=lambda x: x[2]["expectancy"])
            print(f"Worst Expectancy:     {worst_exp[0]} ({worst_exp[2]['expectancy']:+.4f})")

        print()

        # Win rate analysis
        high_wr = [s for s in ranked if s[2]["win_rate_short"] >= 0.6]
        low_wr = [s for s in ranked if s[2]["win_rate_short"] < 0.4]

        print("🎯 WIN RATE ANALYSIS")
        print("-" * 80)
        print(f"High Win Rate (≥60%): {len(high_wr):<4} sensors")
        print(f"Low Win Rate (<40%):  {len(low_wr):<4} sensors")

        if high_wr:
            best_wr = max(high_wr, key=lambda x: x[2]["win_rate_short"])
            print(f"Best Win Rate:        {best_wr[0]} ({best_wr[2]['win_rate_short']:.1%})")

        print()

        # Recommendations
        print("💡 RECOMMENDATIONS")
        print("-" * 80)

        if terrible:
            print(f"⚠️  Consider disabling {len(terrible)} terrible sensors (score < 0.3)")
            for sensor_id, score, stats in terrible[:5]:
                print(f"   - {sensor_id} (score: {score:.3f})")

        if excellent:
            print(f"✅ Focus on {len(excellent)} excellent sensors (score ≥ 0.7)")
            for sensor_id, score, stats in excellent[:5]:
                print(f"   - {sensor_id} (score: {score:.3f})")

        # Insufficient data
        insufficient = [s for s in ranked if s[2]["total_trades"] < 10]
        if insufficient:
            print(f"\n📊 {len(insufficient)} sensors have insufficient data (<10 trades)")

        print()

    def export_csv(self, output_file: Path = Path("sensor_analysis.csv")):
        """Export analysis to CSV."""
        ranked = self.get_ranked_sensors()

        with open(output_file, "w") as f:
            # Header
            f.write(
                "Rank,Sensor,Score,WinRateShort,WinRateMedium,Expectancy,ProfitFactor,"
                "AvgWin,AvgLoss,CurrentStreak,TotalTrades,Wins,Losses\n"
            )

            # Data
            for i, (sensor_id, score, stats) in enumerate(ranked, 1):
                f.write(
                    f"{i},{sensor_id},{score:.4f},"
                    f"{stats['win_rate_short']:.4f},{stats['win_rate_medium']:.4f},"
                    f"{stats['expectancy']:.6f},{stats['profit_factor']:.4f},"
                    f"{stats['avg_win']:.6f},{stats['avg_loss']:.6f},"
                    f"{stats['current_streak']},{stats['total_trades']},"
                    f"{stats['total_wins']},{stats['total_losses']}\n"
                )

        print(f"✅ Exported analysis to {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze sensor tracker memory")
    parser.add_argument("--top", type=int, default=10, help="Number of top sensors to show")
    parser.add_argument("--bottom", type=int, default=10, help="Number of bottom sensors to show")
    parser.add_argument("--detailed", action="store_true", help="Show detailed analysis")
    parser.add_argument("--export", action="store_true", help="Export to CSV")
    parser.add_argument(
        "--stats-file",
        type=Path,
        default=Path("state/sensor_stats.json"),
        help="Path to sensor stats file",
    )

    args = parser.parse_args()

    # Create analyzer
    analyzer = SensorAnalyzer(stats_file=args.stats_file)

    if not analyzer.sensors:
        return

    # Print summary
    analyzer.print_summary()

    # Print top sensors
    analyzer.print_top_sensors(n=args.top)

    # Print bottom sensors
    analyzer.print_bottom_sensors(n=args.bottom)

    # Detailed analysis
    if args.detailed:
        analyzer.print_detailed_analysis()

    # Export to CSV
    if args.export:
        analyzer.export_csv()


if __name__ == "__main__":
    main()
