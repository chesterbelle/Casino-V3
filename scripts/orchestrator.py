import argparse
import glob
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor

# Resolve venv python path for subprocess calls
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_python = os.path.join(_BASE, ".venv", "bin", "python")

# Semaphore to control I/O-intensive initialization
io_semaphore = threading.Semaphore(2)


def handle_exit(signum, frame):
    print(f"\n🛑 Signal {signum} received. Cleaning up processes...")
    # In ProcessPoolExecutor, subprocesses are spawned as children.
    # For now, we rely on the executor to handle shutdown, but we can force exit here.
    os._exit(1)


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


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
        "run_type": "trade",
        "max_workers": 1,
    },
    "single-coin": {
        "run_type": "audit",
        "max_workers": 1,
    },
    "set_a": {
        "datasets": [
            "LTC_TREND_UP_2023-02-01.db",
            "LTC_TREND_UP_2025-05-01.db",
            "LTC_TREND_DOWN_2024-04-01.db",
            "LTC_TREND_DOWN_2024-10-01.db",
            "LTC_BALANCE_2024-02-01.db",
            "LTC_BALANCE_2024-05-01.db",
        ],
        "symbol": "LTC/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": False,
    },
    "set_a_avax": {
        "datasets": [
            "2023-02-01_AVAXUSDT.db",
            "2024-02-01_AVAXUSDT.db",
            "2024-04-01_AVAXUSDT.db",
            "2024-05-01_AVAXUSDT.db",
            "2024-10-01_AVAXUSDT.db",
            "2025-05-01_AVAXUSDT.db",
        ],
        "symbol": "AVAX/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_sui": {
        "datasets": [
            "2024-02-01_SUIUSDT.db",
            "2024-05-01_SUIUSDT.db",
        ],
        "symbol": "SUI/USDT:USDT",
        "run_type": "audit",
        "max_workers": 2,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_sol": {
        "datasets": [
            "2024-05-01_SOLUSDT.db",
            "2024-11-01_SOLUSDT.db",
            "2025-01-01_SOLUSDT.db",
            "2025-02-01_SOLUSDT.db",
            "2025-09-01_SOLUSDT.db",
            "2025-11-01_SOLUSDT.db",
        ],
        "symbol": "SOL/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_xrp": {
        "datasets": [
            "2024-10-01_XRPUSDT.db",
            "2024-11-01_XRPUSDT.db",
            "2025-01-01_XRPUSDT.db",
            "2025-02-01_XRPUSDT.db",
            "2025-04-01_XRPUSDT.db",
            "2025-06-01_XRPUSDT.db",
        ],
        "symbol": "XRP/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_doge": {
        "datasets": [
            "2024-10-01_DOGEUSDT.db",
            "2024-11-01_DOGEUSDT.db",
            "2024-12-01_DOGEUSDT.db",
            "2025-01-01_DOGEUSDT.db",
            "2025-02-01_DOGEUSDT.db",
            "2025-04-01_DOGEUSDT.db",
        ],
        "symbol": "DOGE/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_op": {
        "datasets": [
            "2024-10-01_OPUSDT.db",
            "2024-11-01_OPUSDT.db",
            "2024-12-01_OPUSDT.db",
        ],
        "symbol": "OP/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_link": {
        "datasets": [
            "2024-11-01_LINKUSDT.db",
            "2025-02-01_LINKUSDT.db",
            "2025-06-01_LINKUSDT.db",
            "2025-08-01_LINKUSDT.db",
            "2025-11-01_LINKUSDT.db",
        ],
        "symbol": "LINK/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_near": {
        "datasets": [
            "2024-11-01_NEARUSDT.db",
            "2024-12-01_NEARUSDT.db",
            "2025-02-01_NEARUSDT.db",
            "2025-04-01_NEARUSDT.db",
            "2026-02-01_NEARUSDT.db",
            "2026-05-01_NEARUSDT.db",
        ],
        "symbol": "NEAR/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_apt": {
        "datasets": [
            "2024-10-01_APTUSDT.db",
            "2024-11-01_APTUSDT.db",
            "2024-12-01_APTUSDT.db",
            "2025-04-01_APTUSDT.db",
            "2025-06-01_APTUSDT.db",
            "2025-11-01_APTUSDT.db",
            "2026-05-01_APTUSDT.db",
        ],
        "symbol": "APT/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_btc": {
        "datasets": [
            "2024-11-01_BTCUSDT.db",
            "2025-02-01_BTCUSDT.db",
            "2025-04-01_BTCUSDT.db",
            "2025-10-01_BTCUSDT.db",
            "2025-11-01_BTCUSDT.db",
            "2026-05-01_BTCUSDT.db",
        ],
        "symbol": "BTC/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_eth": {
        "datasets": [
            "2024-08-01_ETHUSDT.db",
            "2024-09-01_ETHUSDT.db",
            "2024-10-01_ETHUSDT.db",
            "2024-11-01_ETHUSDT.db",
            "2025-02-01_ETHUSDT.db",
            "2025-07-01_ETHUSDT.db",
        ],
        "symbol": "ETH/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_ada": {
        "datasets": [
            "2024-11-01_ADAUSDT.db",
            "2025-02-01_ADAUSDT.db",
            "2025-03-01_ADAUSDT.db",
            "2025-07-01_ADAUSDT.db",
            "2025-11-01_ADAUSDT.db",
            "2026-05-01_ADAUSDT.db",
        ],
        "symbol": "ADA/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_arb": {
        "datasets": [
            "2024-11-01_ARBUSDT.db",
            "2025-02-01_ARBUSDT.db",
            "2025-05-01_ARBUSDT.db",
            "2025-06-01_ARBUSDT.db",
            "2025-10-01_ARBUSDT.db",
            "2026-04-01_ARBUSDT.db",
        ],
        "symbol": "ARB/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_a_bnb": {
        "datasets": [
            "2024-05-01_BNBUSDT.db",
            "2025-01-01_BNBUSDT.db",
            "2025-07-01_BNBUSDT.db",
            "2025-09-01_BNBUSDT.db",
            "2025-11-01_BNBUSDT.db",
            "2026-02-01_BNBUSDT.db",
        ],
        "symbol": "BNB/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": True,
        "skip_clean": True,
    },
    "set_b": {
        "datasets": [
            "LTC_TREND_UP_2025-10-01.db",
            "LTC_TREND_UP_2024-03-01.db",
            "LTC_TREND_DOWN_2025-12-01.db",
            "LTC_TREND_DOWN_2025-02-01.db",
            "LTC_BALANCE_2023-08-01.db",
            "LTC_BALANCE_2025-03-01.db",
        ],
        "symbol": "LTC/USDT:USDT",
        "run_type": "audit",
        "max_workers": 3,
        "skip_merge": False,
    },
}

DB_DIR = "data/datasets/backtest_ready"
LOG_DIR = "logs"


def clean_temp_data():
    print("🧹 Cleaning historian databases...")
    for f in glob.glob("data/historian_*.db"):
        try:
            os.remove(f)
        except OSError:
            pass
    for f in glob.glob("data/historian.db*"):
        try:
            os.remove(f)
        except OSError:
            pass
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)


def clean_temp_data_selective(keep_patterns=None):
    """
    Like clean_temp_data, but only removes files matching the orchestrator's
    own dataset pattern. Used by skip_clean protocols to avoid wiping
    per-dataset DBs owned by sibling/parallel processes.
    """
    if keep_patterns is None:
        keep_patterns = []
    print("🧹 Selective cleaning of temp historian_*.db (preserving siblings)...")
    for f in glob.glob("data/historian_*.db"):
        if any(k in f for k in keep_patterns):
            continue
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
    pattern = os.path.join(DB_DIR, f"*{asset_or_db}*.db")
    matches = glob.glob(pattern)
    if len(matches) == 0:
        raise FileNotFoundError(f"No DB found for {asset_or_db} in {DB_DIR}")
    elif len(matches) > 1:
        raise ValueError(f"AMBIGUOUS: Found {len(matches)} DBs for {asset_or_db} in {DB_DIR}. Keep exactly 1.")
    return matches[0]


def format_ccxt_symbol(sym):
    if "/" in sym:
        return sym
    if sym.endswith("USDT"):
        base = sym[:-4]
        return f"{base}/USDT:USDT"
    return sym


def run_backtest_task(task_config):
    # Acquire semaphore to throttle DB initialization phase
    with io_semaphore:
        db_path = task_config["db_path"]
        symbol = task_config["symbol"]
        run_type = task_config["run_type"]
        task_id = task_config["task_id"]

        historian_db = f"data/historian_{task_id}.db"
        log_file = os.path.join(LOG_DIR, f"orchestrator_{task_id}.log")

        cmd = [
            venv_python,
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
            env = os.environ.copy()
            env["CASINO_HISTORIAN_DB"] = historian_db
            process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
            task_config["process"] = process
            task_config["historian_db"] = historian_db
            task_config["log_file"] = log_file

            # Guardamos timestamps para el deadlock watchdog
            task_config["last_size"] = 0
            task_config["last_progress_time"] = time.time()

            process.wait()

    return process.returncode == 0


def run_protocol(protocol_name, symbol=None):
    config_preview = PROTOCOLS.get(protocol_name, {})
    if not config_preview.get("skip_clean", False):
        clean_temp_data()
    else:
        # skip_clean=True: do NOT delete any historian_*.db files.
        # Sibling/parallel protocol DBs (e.g., SUI writing while AVAX starts)
        # MUST be preserved. Only ensure log dir exists.
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
    print(f"🚀 Starting protocol: {protocol_name}")
    # CRITICAL: When skip_clean=True, only clean files matching this protocol's
    # own datasets. Sibling/parallel protocol DBs (e.g., SUI running while AVAX
    # starts) must be preserved. Re-cleaning here with pattern is a no-op since
    # the global clean above already happened; the real protection is that we
    # do NOT re-clean mid-run.
    if config_preview.get("skip_clean", False):
        print("   🔒 skip_clean=True — sibling DBs from other protocols will be preserved")

    config = PROTOCOLS.get(protocol_name)
    if not config:
        print(f"❌ Unknown protocol: {protocol_name}")
        return

    tasks = []
    if protocol_name in (
        "long-range",
        "cross-validation",
        "set_a",
        "set_b",
        "set_a_avax",
        "set_a_sui",
        "set_a_sol",
        "set_a_xrp",
        "set_a_doge",
        "set_a_op",
        "set_a_link",
        "set_a_near",
        "set_a_apt",
        "set_a_btc",
        "set_a_eth",
        "set_a_ada",
        "set_a_arb",
        "set_a_bnb",
    ):
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
    with ProcessPoolExecutor(max_workers=config["max_workers"]) as executor:
        for t in tasks:
            future = executor.submit(run_backtest_task, t)
            futures_map[future] = t

        # Monitor Loop — checks future.done() for ProcessPoolExecutor
        completed_tasks = set()
        while len(completed_tasks) < len(tasks):
            time.sleep(30)

            if os.environ.get("TERM"):
                os.system("clear" if os.name == "posix" else "cls")
            print(f"=== ⚙️  Smart Orchestrator: {protocol_name.upper()} ===")
            print(f"Status: {len(completed_tasks)}/{len(tasks)} completed.\n")

            for future, t in futures_map.items():
                task_id = t["task_id"]
                if future.done():
                    if task_id not in completed_tasks:
                        try:
                            success = future.result()
                            print(f"{'✅ SUCCESS' if success else '❌ FAILED'} {task_id}")
                            completed_tasks.add(task_id)
                        except Exception as e:
                            print(f"❌ ERROR {task_id}: {e}")
                            completed_tasks.add(task_id)
                else:
                    hist_db = f"data/historian_{task_id}.db"
                    size_str = "0 MB"
                    if os.path.exists(hist_db):
                        size_mb = os.path.getsize(hist_db) / (1024 * 1024)
                        size_str = f"{size_mb:.2f} MB"
                    print(f"🔄 {task_id}: Processing... (DB Size: {size_str})")

        results = [f.result() for f in futures_map.keys()]

    if all(results):
        print(f"\n🎉 All backtests for {protocol_name} complete.")

        skip_merge = config.get("skip_merge", False)
        if config["run_type"] == "audit" and protocol_name != "single-coin" and not skip_merge:
            print("🔗 Merging historian databases...")
            subprocess.run([venv_python, "utils/merge_historian.py"])

            print("📊 Running full edge auditor analysis...")
            subprocess.run([venv_python, "utils/setup_edge_auditor.py", "--window", "14400"])
        elif skip_merge:
            print("⏭️  Merge skipped (skip_merge=True). Run merge manually after all protocols complete.")

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
