#!/usr/bin/env python3
"""Monitor orchestrator progress every 60s and report to user."""
import os
import subprocess
import sys
import time

LOG_FILE = "logs/orchestrator_run.log"


def check():
    # Check orchestrator
    orch = subprocess.run(
        ["ps", "-p", "176811", "-o", "pid,pgid,stat,etime", "--no-headers"], capture_output=True, text=True, timeout=5
    )
    if not orch.stdout.strip():
        print("❌ Orchestrator DEAD")
        tail = subprocess.run(["tail", "-20", LOG_FILE], capture_output=True, text=True, timeout=5)
        print(tail.stdout)
        return False

    # Count backtest processes
    bt = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
    bt_lines = [line for line in bt.stdout.split("\n") if "backtest.py" in line and "grep" not in line]
    bt_main = [line for line in bt_lines if "backtest.py --depth" in line]

    # DB file sizes
    db_info = []
    for f in sorted(os.listdir("data")):
        if f.startswith("historian_") and f.endswith(".db"):
            size = os.path.getsize(f"data/{f}")
            db_info.append((f, size // 1024))

    # Log tail
    log_tail = subprocess.run(["tail", "-5", LOG_FILE], capture_output=True, text=True, timeout=5)

    print(
        f"🟢  UP {orch.stdout.strip().split()[-1]}  |  Backtests: {len(bt_main)} active  |  DBs: {len(db_info)} files"
    )
    for name, size_kb in db_info:
        flag = "🔄" if size_kb <= 48 else "✅" if size_kb > 100 else "⏳"
        print(f"  {flag} {name}: {size_kb}K")

    recent = log_tail.stdout.strip()
    if recent:
        last_lines = [line for line in recent.split("\n") if line.strip()]
        if last_lines:
            print(f"  📋 {last_lines[-1]}")

    return True


def monitor(interval=120):
    print("=" * 60)
    print("📊 MONITORING GENERALIZED PROTOCOL")
    print(f"   Check every {interval}s  |  Orchestrator PID: 176811")
    print("=" * 60)
    while True:
        time.sleep(interval)
        if not check():
            break
        print("-" * 40)


if __name__ == "__main__":
    monitor(interval=int(sys.argv[1]) if len(sys.argv) > 1 else 120)
