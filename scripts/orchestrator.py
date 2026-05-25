import argparse
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

# Protocol Configurations
PROTOCOLS = {
    "generalized": {
        "assets": [
            "ADAUSDT",
            "ETHUSDT",
            "SOLUSDT",
            "BNBUSDT",
            "BTCUSDT",
            "AVAXUSDT",
            "LINKUSDT",
            "DOGEUSDT",
            "LTCUSDT",
            "SUIUSDT",
        ],
        "run_type": "audit",
        "max_workers": 4,
    },
    "long-range": {
        # Explicit files required by the workflow
        "datasets": [
            "LTC_RANGE_2024-02-01.db",
            "LTC_RANGE_2024-05-01.db",
            "LTC_RANGE_2024-08-01.db",
            "LTC_BEAR_2024-04-01.db",
            "LTC_BEAR_2024-10-01.db",
            "LTC_BEAR_2025-02-01.db",
            "LTC_BULL_2024-03-01.db",
            "LTC_BULL_2024-12-01.db",
            "LTC_BULL_2025-05-01.db",
        ],
        "symbol": "LTC/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
    },
    "strategy": {
        # The user will pass the symbol via --symbol
        "run_type": "trade",
        "max_workers": 1,
    },
    "single-coin": {
        # The user will pass the symbol via --symbol
        "run_type": "audit",
        "max_workers": 1,
    },
}

DB_DIR = "data/datasets/backtest_ready"
LOG_DIR = "logs"


def clean_temp_data():
    print("🧹 Cleaning temporary historian databases...")
    for f in glob.glob("data/historian_*.db"):
        try:
            os.remove(f)
        except OSError:
            pass
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)


def strict_find_db(asset_or_db):
    if asset_or_db.endswith(".db"):
        path = os.path.join(DB_DIR, asset_or_db)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing required dataset: {path}")
        return path

    # It's an asset like BTCUSDT
    pattern = os.path.join(DB_DIR, f"*{asset_or_db}*.db")
    matches = glob.glob(pattern)
    if len(matches) == 0:
        raise FileNotFoundError(f"No DB found for {asset_or_db} in {DB_DIR}")
    elif len(matches) > 1:
        raise ValueError(
            f"AMBIGUOUS: Found {len(matches)} DBs for {asset_or_db} in {DB_DIR}. Keep exactly 1 to avoid executing the wrong data."
        )
    return matches[0]


def format_ccxt_symbol(sym):
    if "/" in sym:
        return sym
    if sym.endswith("USDT"):
        base = sym[:-4]
        return f"{base}/USDT:USDT"
    return sym


def run_backtest_task(task_config):
    db_path = task_config["db_path"]
    symbol = task_config["symbol"]
    run_type = task_config["run_type"]
    task_id = task_config["task_id"]

    historian_db = f"data/historian_{task_id}.db"
    log_file = os.path.join(LOG_DIR, f"orchestrator_{task_id}.log")

    cmd = [
        sys.executable,
        "backtest.py",
        "--depth-db-path",
        db_path,
        "--run-type",
        run_type,
        "--symbol",
        symbol,
        "--historian-db",
        historian_db,
    ]

    with open(log_file, "w") as f:
        process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        task_config["process"] = process
        task_config["historian_db"] = historian_db
        task_config["log_file"] = log_file

        # Guardamos timestamps para el deadlock watchdog
        task_config["last_size"] = 0
        task_config["last_progress_time"] = time.time()

        process.wait()

    return process.returncode == 0


def run_protocol(protocol_name, symbol=None):
    clean_temp_data()
    print(f"🚀 Starting protocol: {protocol_name}")

    config = PROTOCOLS.get(protocol_name)
    if not config:
        print(f"❌ Unknown protocol: {protocol_name}")
        return

    tasks = []
    if protocol_name == "long-range":
        for db_file in config["datasets"]:
            tasks.append(
                {
                    "task_id": db_file.replace(".db", ""),
                    "db_path": strict_find_db(db_file),
                    "symbol": config["symbol"],
                    "run_type": config["run_type"],
                }
            )
    elif protocol_name in ["single-coin", "strategy"]:
        if not symbol:
            symbol = "LTCUSDT"  # default if not provided
        tasks.append(
            {
                "task_id": symbol,
                "db_path": strict_find_db(symbol),
                "symbol": format_ccxt_symbol(symbol),
                "run_type": config["run_type"],
            }
        )
    else:  # generalized
        for asset in config["assets"]:
            tasks.append(
                {
                    "task_id": asset,
                    "db_path": strict_find_db(asset),
                    "symbol": format_ccxt_symbol(asset),
                    "run_type": config["run_type"],
                }
            )

    futures_map = {}
    with ThreadPoolExecutor(max_workers=config["max_workers"]) as executor:
        for t in tasks:
            future = executor.submit(run_backtest_task, t)
            futures_map[future] = t

        # Monitor Loop
        completed_tasks = set()
        while len(completed_tasks) < len(tasks):
            time.sleep(5)

            os.system("clear" if os.name == "posix" else "cls")
            print(f"=== ⚙️  Smart Orchestrator: {protocol_name.upper()} ===")
            print(f"Status: {len(completed_tasks)}/{len(tasks)} completed.\n")

            for t in tasks:
                task_id = t["task_id"]
                process = t.get("process")
                hist_db = t.get("historian_db", "")

                if process is None:
                    print(f"⏳ {task_id}: Waiting in queue...")
                    continue

                if process.poll() is not None:  # Finished
                    if task_id not in completed_tasks:
                        completed_tasks.add(task_id)
                    status = "✅ SUCCESS" if process.returncode == 0 else "❌ FAILED"
                    print(f"{status} {task_id}")
                else:  # Running
                    size_str = "0 MB"
                    current_size = 0
                    if os.path.exists(hist_db):
                        current_size = os.path.getsize(hist_db)
                        size_mb = current_size / (1024 * 1024)
                        size_str = f"{size_mb:.2f} MB"

                    # Watchdog logic
                    if current_size > t.get("last_size", 0):
                        t["last_size"] = current_size
                        t["last_progress_time"] = time.time()

                    stalled_seconds = time.time() - t.get("last_progress_time", time.time())

                    if stalled_seconds > 120:
                        print(f"⚠️ {task_id}: WARNING STALLED for {int(stalled_seconds)}s! (DB Size: {size_str})")
                    else:
                        print(f"🔄 {task_id}: Processing... (DB Size: {size_str})")

        results = [f.result() for f in futures_map.keys()]

    if all(results):
        print(f"\n🎉 All backtests for {protocol_name} complete.")

        if config["run_type"] == "audit" and protocol_name != "single-coin":
            print("🔗 Merging historian databases...")
            subprocess.run([sys.executable, "utils/merge_historian.py"])

            print("📊 Running full edge auditor analysis...")
            subprocess.run([sys.executable, "utils/setup_edge_auditor.py", "--window", "14400"])

        print("✅ Protocol complete.")
    else:
        print("\n❌ Some backtests failed. Check the logs in the logs/ directory.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Orchestrator for Casino-V3 Audit Protocols")
    parser.add_argument("--protocol", choices=PROTOCOLS.keys(), required=True)
    parser.add_argument("--symbol", help="Symbol for single-coin or strategy protocol (e.g. LTCUSDT)")
    args = parser.parse_args()

    try:
        run_protocol(args.protocol, args.symbol)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        sys.exit(1)
