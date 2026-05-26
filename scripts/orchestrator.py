import argparse
import glob
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor

# Semaphore to control I/O-intensive initialization
io_semaphore = threading.Semaphore(2)


def handle_exit(signum, frame):
    print(f"\n🛑 Signal {signum} received. Cleaning up processes...")
    # In ProcessPoolExecutor, subprocesses are spawned as children.
    # For now, we rely on the executor to handle shutdown, but we can force exit here.
    os._exit(1)


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


# ... (rest of code)
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
    with ProcessPoolExecutor(max_workers=config["max_workers"]) as executor:
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
