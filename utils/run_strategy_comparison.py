#!/usr/bin/env python3
"""
Run backtests for each strategy and compare results.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

# Strategies to test
STRATEGIES = [
    "TrendRider",
    "MeanReverter",
    "BreakoutHunter",
    "QuickScalper",
    "SmartMoneyFollower",
    "PatternTrader",
    "DebugAll",
]

DATA_FILE = "data/raw/LTCUSDT_1m__30d.csv"
SYMBOL = "LTCUSDT"


def enable_strategy(strategy_name: str):
    """Enable only the specified strategy in config."""
    config_path = Path("config/strategies.py")
    content = config_path.read_text()

    # Pattern to match strategy definitions
    for strat in STRATEGIES:
        # Replace enabled status
        if strat == strategy_name:
            # Enable this strategy
            content = re.sub(rf'("{strat}":\s*{{\s*"enabled":\s*)False', rf"\1True", content)
        else:
            # Disable other strategies
            content = re.sub(rf'("{strat}":\s*{{\s*"enabled":\s*)True', rf"\1False", content)

    config_path.write_text(content)


def run_backtest():
    """Run backtest and capture results."""
    cmd = [sys.executable, "backtest.py", f"--data={DATA_FILE}", f"--symbol={SYMBOL}"]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    output = result.stdout + result.stderr
    return output


def parse_results(output: str) -> dict:
    """Extract key metrics from backtest output."""
    results = {}

    # Parse wins/losses
    match = re.search(r"Wins / Losses\s*:\s*(\d+)\s*/\s*(\d+)", output)
    if match:
        results["wins"] = int(match.group(1))
        results["losses"] = int(match.group(2))
        total = results["wins"] + results["losses"]
        results["total_trades"] = total
        results["win_rate"] = (results["wins"] / total * 100) if total > 0 else 0

    # Parse PnL
    match = re.search(r"PnL Total\s*:\s*([\+\-]?\d+\.?\d*)", output)
    if match:
        results["pnl"] = float(match.group(1))

    # Parse Balance
    match = re.search(r"Balance final\s*:\s*([\d\.]+)", output)
    if match:
        results["final_balance"] = float(match.group(1))

    return results


def main():
    print("=" * 60)
    print("🎲 CASINO-V3 STRATEGY COMPARISON")
    print("=" * 60)
    print(f"📊 Dataset: {DATA_FILE}")
    print(f"💱 Symbol: {SYMBOL}")
    print("=" * 60 + "\n")

    all_results = {}

    for strategy in STRATEGIES:
        print(f"\n🔄 Testing strategy: {strategy}...")

        # Enable only this strategy
        enable_strategy(strategy)

        # Run backtest
        try:
            output = run_backtest()
            results = parse_results(output)
            results["strategy"] = strategy
            all_results[strategy] = results

            print(
                f"   ✅ Wins: {results.get('wins', 0)} | "
                f"Losses: {results.get('losses', 0)} | "
                f"WR: {results.get('win_rate', 0):.1f}% | "
                f"PnL: {results.get('pnl', 0):+.2f}"
            )
        except Exception as e:
            print(f"   ❌ Error: {e}")
            all_results[strategy] = {"strategy": strategy, "error": str(e)}

    # Summary table
    print("\n" + "=" * 60)
    print("📊 RESULTS SUMMARY")
    print("=" * 60)
    print(f"{'Strategy':<20} {'Trades':>8} {'Wins':>6} {'Losses':>6} {'WR%':>8} {'PnL':>10}")
    print("-" * 60)

    sorted_results = sorted(all_results.values(), key=lambda x: x.get("pnl", float("-inf")), reverse=True)

    for r in sorted_results:
        if "error" in r:
            print(f"{r['strategy']:<20} {'ERROR':<40}")
        else:
            print(
                f"{r['strategy']:<20} "
                f"{r.get('total_trades', 0):>8} "
                f"{r.get('wins', 0):>6} "
                f"{r.get('losses', 0):>6} "
                f"{r.get('win_rate', 0):>7.1f}% "
                f"{r.get('pnl', 0):>+10.2f}"
            )

    print("=" * 60)

    # Save results
    output_file = Path("logs/strategy_comparison.json")
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n💾 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
