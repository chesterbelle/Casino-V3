import os
import re
import shutil
import subprocess

CONFIG_PATH = "config/trading.py"
BACKUP_PATH = "config/trading.py.bak"

SCENARIOS = [
    {"name": "RAW", "so": False, "be": False, "ts": False, "di": False},
    {"name": "Scale Out", "so": True, "be": False, "ts": False, "di": False},
    {"name": "Break Even", "so": False, "be": True, "ts": False, "di": False},
    {"name": "Trailing", "so": False, "be": False, "ts": True, "di": False},
    {"name": "Delta Inval", "so": False, "be": False, "ts": False, "di": True},
    {"name": "All Pillars", "so": True, "be": True, "ts": True, "di": True},
]


def strip_ansi(text):
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def update_config(so, be, ts, di):
    with open(BACKUP_PATH, "r") as f:
        content = f.read()

    # Regex to find the LIQUID_ALT block and update its enabled flags
    liquid_alt_pattern = r'("LIQUID_ALT":\s*{.*?})'

    def replace_flags(match):
        block = match.group(1)
        block = re.sub(r'("scale_out":\s*{\s*"enabled":\s*)True|False', rf"\1{str(so)}", block)
        block = re.sub(r'("break_even":\s*{\s*"enabled":\s*)True|False', rf"\1{str(be)}", block)
        block = re.sub(r'("trailing":\s*{\s*"enabled":\s*)True|False', rf"\1{str(ts)}", block)
        block = re.sub(r'("delta_invalidation":\s*{\s*"enabled":\s*)True|False', rf"\1{str(di)}", block)
        return block

    new_content = re.sub(liquid_alt_pattern, replace_flags, content, flags=re.DOTALL)

    with open(CONFIG_PATH, "w") as f:
        f.write(new_content)


def run_cmd(cmd):
    print(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr


def parse_metrics(output):
    output = strip_ansi(output)
    metrics = {"WR": "N/A", "PF": "N/A", "Trades": "N/A", "Net PnL": "N/A"}

    # Focus on the OVERALL METRICS section
    overall_part = output.split("OVERALL METRICS")[-1].split("[2]")[0]

    wr_match = re.search(r"Win Rate\s*:\s*([\d.]+%?)", overall_part)
    pf_match = re.search(r"Profit Factor\s*:\s*([\d.]+)", overall_part)
    trades_match = re.search(r"Active Trades\s*:\s*(\d+)", overall_part)
    pnl_match = re.search(r"Active PnL\s*:\s*\$?\s*([-\d.]+)", overall_part)

    if wr_match:
        metrics["WR"] = wr_match.group(1)
    if pf_match:
        metrics["PF"] = pf_match.group(1)
    if trades_match:
        metrics["Trades"] = trades_match.group(1)
    if pnl_match:
        metrics["Net PnL"] = pnl_match.group(1)

    return metrics


results = []

try:
    if not os.path.exists(BACKUP_PATH):
        shutil.copy(CONFIG_PATH, BACKUP_PATH)

    for s in SCENARIOS:
        print(f"\n>>> RUNNING SCENARIO: {s['name']} <<<")
        update_config(s["so"], s["be"], s["ts"], s["di"])

        # Step 0: Reset
        run_cmd(".venv/bin/python reset_data.py && .venv/bin/python utils/strategy_audit.py --reset-db")

        # Step 1: Backtest
        # Using symbol LTC/USDT:USDT as per workflow
        run_cmd(
            ".venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_LTCUSDT.db --symbol LTC/USDT:USDT"
        )

        # Step 2: Analyze
        output = run_cmd(".venv/bin/python utils/strategy_audit.py")

        # Log the output for debugging
        log_name = f".agent/scratch/audit_{s['name'].replace(' ', '_')}.log"
        with open(log_name, "w") as f:
            f.write(output)

        metrics = parse_metrics(output)
        metrics["Scenario"] = s["name"]
        results.append(metrics)

        print(
            f"Result for {s['name']}: WR={metrics['WR']}, PF={metrics['PF']}, Trades={metrics['Trades']}, PnL={metrics['Net PnL']}"
        )

finally:
    # Restore config
    if os.path.exists(BACKUP_PATH):
        shutil.copy(BACKUP_PATH, CONFIG_PATH)

# Final Table
print("\n" + "=" * 80)
print(f"{'Scenario':<15} | {'WR':<8} | {'PF':<6} | {'Trades':<8} | {'Net PnL':<10}")
print("-" * 80)
for r in results:
    print(f"{r['Scenario']:<15} | {r['WR']:<8} | {r['PF']:<6} | {r['Trades']:<8} | {r['Net PnL']:<10}")
print("=" * 80)
