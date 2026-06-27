#!/usr/bin/env python3
"""
A/B Test: Absorption Score v1 (thresholds fijos) vs v2 (z-score auto-calibrado).

Uso:
  python scripts/ab_absorption_mode.py

Ejecuta backtest de 1 dataset por coin (SOL, AVAX, XRP) con cada modo,
mergea por modo, y corre el edge auditor. Compara Net Taker de T_ACC.
"""

import glob
import os
import shutil
import subprocess
from pathlib import Path

COINS = ["SOL", "AVAX", "XRP"]
BACKTEST_READY = "data/datasets/daily_backtest_ready"
VENV_PYTHON = ".venv/bin/python"
TASK_TIMEOUT = 14400
AB_DIR = "data/ab_test"


def pick_recent_dataset(sym: str) -> str:
    files = sorted(Path(BACKTEST_READY).glob(f"*_{sym}USDT.db"))
    if not files:
        return None
    return str(files[-1])


def clean_temp_historians(skip: str = None):
    for f in glob.glob("data/historian_*.db"):
        if skip and f == skip:
            continue
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
        for ext in ["-wal", "-shm"]:
            p = f + ext
            if os.path.exists(p):
                os.remove(p)


def run_backtest(db_path: str, symbol: str, historian_db: str, mode: str) -> bool:
    cmd = [
        VENV_PYTHON,
        "-u",
        "backtest.py",
        "--depth-db-path",
        db_path,
        "--run-type",
        "audit",
        "--symbol",
        f"{symbol}/USDT:USDT",
        "--historian-db",
        historian_db,
    ]
    env = os.environ.copy()
    env["CASINO_HISTORIAN_DB"] = historian_db
    env["CASINO_ABSORPTION_MODE"] = mode
    log_file = f"logs/ab_{symbol}_{mode}.log"
    os.makedirs("logs", exist_ok=True)
    print(f"  Backtest {symbol} mode={mode}...", end=" ", flush=True)
    try:
        with open(log_file, "w") as f:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
            proc.wait(timeout=TASK_TIMEOUT)
        ok = proc.returncode == 0
        print("OK" if ok else "FAIL")
        return ok
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print("TIMEOUT")
        return False


def main():
    print("=" * 60)
    print("  A/B TEST: Absorption Score v1 (thresholds) vs v2 (z-score)")
    print("=" * 60)

    os.makedirs(AB_DIR, exist_ok=True)

    # Stash any existing historian.db so merge_historian.py doesn't pollute it
    if os.path.exists("data/historian.db"):
        backup = "data/historian.db.bak.ab"
        shutil.move("data/historian.db", backup)
        print(f"  Stashed existing data/historian.db → {backup}")

    for mode in ["v1", "v2"]:
        print(f"\n{'─'*50}")
        print(f"  PHASE: mode={mode}")
        print(f"{'─'*50}")
        clean_temp_historians()

        # 1. Backtest ALL coins for this mode
        for coin in COINS:
            ds = pick_recent_dataset(coin)
            if not ds:
                print(f"  No dataset for {coin}, skipping")
                continue
            historian_part = f"data/historian_{coin}_ab_{mode}.db"
            ok = run_backtest(ds, coin, historian_part, mode)
            if not ok:
                print(f"  Backtest FAILED for {coin} mode={mode}, continuing")

        # 2. Merge all temps → data/historian.db
        temps = glob.glob(f"data/historian_*_ab_{mode}.db")
        if not temps:
            print(f"  No temp historians for mode={mode}, skipping merge")
            continue
        print(f"  Merging {len(temps)} temps...", end=" ", flush=True)
        r = subprocess.run(
            [VENV_PYTHON, "utils/merge_historian.py"],
            capture_output=True,
            text=True,
        )
        print("OK" if r.returncode == 0 else "FAIL")

        # 3. Rename data/historian.db → data/ab_test/historian_ab_{mode}.db
        master = f"{AB_DIR}/historian_ab_{mode}.db"
        if os.path.exists("data/historian.db"):
            shutil.move("data/historian.db", master)
            print(f"  → {master}")

        # 4. Wipe all temp historians for this mode
        clean_temp_historians(skip=master)
        for f in glob.glob(f"data/historian_*_ab_{mode}.db"):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
            for ext in ["-wal", "-shm"]:
                p = f + ext
                if os.path.exists(p):
                    os.remove(p)

    # Run edge auditor on both
    print(f"\n{'─'*50}")
    print("  EDGE AUDITOR (both modes)")
    print(f"{'─'*50}")
    for mode in ["v1", "v2"]:
        db = f"{AB_DIR}/historian_ab_{mode}.db"
        if not os.path.exists(db):
            print(f"  {db} not found, skipping")
            continue
        print(f"\n  EdgeAuditor mode={mode} on {db}")
        subprocess.run(
            [VENV_PYTHON, "utils/setup_edge_auditor.py", "--window", "21600", "--db", db],
        )

    # Restore stashed historian.db
    backup = "data/historian.db.bak.ab"
    if os.path.exists(backup):
        shutil.move(backup, "data/historian.db")
        print("\n  Restored data/historian.db from backup")

    print(f"\n{'='*60}")
    print("  DONE — Resultados en data/ab_test/")
    print("    data/ab_test/historian_ab_v1.db  (legacy thresholds)")
    print("    data/ab_test/historian_ab_v2.db  (z-score auto-calibrado)")
    print("  Compara T_ACC por coin:")
    print("    python utils/setup_edge_auditor.py --db data/ab_test/historian_ab_v1.db --by-coin --window 21600")
    print("    python utils/setup_edge_auditor.py --db data/ab_test/historian_ab_v2.db --by-coin --window 21600")
    print("=" * 60)


if __name__ == "__main__":
    main()
