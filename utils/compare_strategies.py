import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.strategies import STRATEGIES

CONFIG_PATH = ROOT / "config" / "strategies.py"
BACKUP_PATH = ROOT / "config" / "strategies.py.bak"


def backup_config():
    shutil.copy(CONFIG_PATH, BACKUP_PATH)


def restore_config():
    if BACKUP_PATH.exists():
        shutil.move(BACKUP_PATH, CONFIG_PATH)


def set_active_strategy(target_strategy):
    with open(CONFIG_PATH, "r") as f:
        content = f.read()

    # Reset all to False
    content = re.sub(r'"enabled":\s*True,', '"enabled": False,', content)

    # Enable target
    # We look for the strategy definition and set its enabled flag
    # This regex assumes standard formatting: "Name": {\n ... "enabled": False,
    # pattern = f'"{target_strategy}":\s*{{\s*"enabled":\s*False,'  # Removed unused variable

    # Try to find the specific block
    # Using a more robust regex to handle whitespace
    pattern = re.compile(rf'"{target_strategy}":\s*\{{\s*"enabled":\s*False,', re.MULTILINE)

    if not pattern.search(content):
        # Maybe it was already True (from the reset step? No, we reset all to False)
        # Or maybe formatting is different.
        print(f"⚠️ Could not find disabled entry for {target_strategy}. Checking if it's already enabled...")
        pattern_true = re.compile(rf'"{target_strategy}":\s*\{{\s*"enabled":\s*True,', re.MULTILINE)
        if pattern_true.search(content):
            print(f"   {target_strategy} is already enabled (unexpected after reset).")
        else:
            print(f"❌ Failed to enable {target_strategy}. Regex mismatch.")
            return False

    content = pattern.sub(f'"{target_strategy}": {{\n        "enabled": True,', content)

    with open(CONFIG_PATH, "w") as f:
        f.write(content)
    return True


def run_backtest(symbol, data_file):
    cmd = [sys.executable, str(ROOT / "backtest.py"), f"--symbol={symbol}", f"--data={data_file}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


def parse_results(output):
    pnl = 0.0
    win_rate = 0.0
    trades = 0

    # Parse PnL Total             : +2.36 (+0.02%)
    pnl_match = re.search(r"PnL Total\s*:\s*([\+\-\d\.]+)", output)
    if pnl_match:
        pnl = float(pnl_match.group(1))

    # Parse Wins / Losses         : 20 / 16
    wl_match = re.search(r"Wins / Losses\s*:\s*(\d+)\s*/\s*(\d+)", output)
    if wl_match:
        wins = int(wl_match.group(1))
        losses = int(wl_match.group(2))
        trades = wins + losses
        if trades > 0:
            win_rate = (wins / trades) * 100

    return {"pnl": pnl, "win_rate": win_rate, "trades": trades}


def main():
    print("🚀 Starting Strategy Comparison...")
    backup_config()

    strategies = list(STRATEGIES.keys())
    results = {}

    data_file = "data/raw/LTCUSDT_1m__30d.csv"
    symbol = "LTCUSDT"

    try:
        for strategy in strategies:
            print(f"\n🧪 Testing Strategy: {strategy}")
            if not set_active_strategy(strategy):
                continue

            output = run_backtest(symbol, data_file)
            stats = parse_results(output)
            results[strategy] = stats

            print(f"   Trades: {stats['trades']} | WR: {stats['win_rate']:.1f}% | PnL: {stats['pnl']:.2f}")

    finally:
        restore_config()
        print("\n✅ Config restored.")

    print("\n" + "=" * 60)
    print(f"{'STRATEGY':<25} | {'TRADES':<8} | {'WIN RATE':<10} | {'PnL':<10}")
    print("-" * 60)

    sorted_results = sorted(results.items(), key=lambda x: x[1]["pnl"], reverse=True)

    for name, stats in sorted_results:
        print(f"{name:<25} | {stats['trades']:<8} | {stats['win_rate']:>8.1f}% | {stats['pnl']:>9.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
