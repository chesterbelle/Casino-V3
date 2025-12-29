import json
import sys
from pathlib import Path

import pandas as pd

# Add parent directory to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.strategies import STRATEGIES


def load_stats():
    path = ROOT / "state" / "sensor_stats.json"
    if not path.exists():
        print("❌ state/sensor_stats.json not found")
        return {}
    with open(path, "r") as f:
        return json.load(f)


def analyze_strategy(strategy_name, stats):
    if strategy_name not in STRATEGIES:
        print(f"❌ Strategy {strategy_name} not found")
        return

    config = STRATEGIES[strategy_name]
    sensors = config["sensors"]

    print(f"\n📊 ANALYSIS: {strategy_name}")
    print(f"   Logic: {config['logic']}")
    print("-" * 60)
    print(f"{'SENSOR':<25} | {'TRADES':<8} | {'WIN RATE':<10} | {'EXPECTANCY':<12} | {'PROFIT FACTOR':<12}")
    print("-" * 60)

    total_trades = 0
    weighted_expectancy = 0

    sensor_data = []

    for sensor in sensors:
        if sensor in stats:
            s = stats[sensor]
            trades = s.get("total_trades", 0)
            # Use win_rate_medium as a proxy for overall win rate if total_wins not explicit
            # Or calculate from wins/losses if available
            wins = s.get("total_wins", 0)
            losses = s.get("total_losses", 0)

            if trades == 0 and (wins + losses) > 0:
                trades = wins + losses

            wr = (wins / trades * 100) if trades > 0 else 0
            exp = s.get("expectancy", 0)
            pf = s.get("profit_factor", 0)

            print(f"{sensor:<25} | {trades:<8} | {wr:>9.1f}% | {exp:>11.4f} | {pf:>11.2f}")

            sensor_data.append({"name": sensor, "trades": trades, "wr": wr, "exp": exp, "pf": pf})

            total_trades += trades
            weighted_expectancy += exp * trades

    print("-" * 60)
    avg_exp = (weighted_expectancy / total_trades) if total_trades > 0 else 0
    print(f"{'TOTAL / AVG':<25} | {total_trades:<8} | {'-':>10} | {avg_exp:>11.4f}")

    return sensor_data


def main():
    stats = load_stats()

    print("🔍 COMPARING STRATEGIES")

    pt_data = analyze_strategy("PatternTrader", stats)
    qs_data = analyze_strategy("QuickScalper", stats)

    # Compare top contributors
    print("\n🏆 TOP CONTRIBUTORS COMPARISON")

    print(f"\nPatternTrader Top 3:")
    pt_sorted = sorted(pt_data, key=lambda x: x["exp"], reverse=True)[:3]
    for s in pt_sorted:
        print(f"   {s['name']}: Exp {s['exp']:.4f} ({s['trades']} trades)")

    print(f"\nQuickScalper Top 3:")
    qs_sorted = sorted(qs_data, key=lambda x: x["exp"], reverse=True)[:3]
    for s in qs_sorted:
        print(f"   {s['name']}: Exp {s['exp']:.4f} ({s['trades']} trades)")


if __name__ == "__main__":
    main()
