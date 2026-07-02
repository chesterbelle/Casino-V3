#!/usr/bin/env python3
"""
===============================================================================
🎯 BACKTEST RUNNER — Unified Backtest Execution Engine
===============================================================================

Two modes of operation:

  AUDIT MODE (Parallel):
    - Executes multiple backtests simultaneously
    - Merges historian databases
    - Runs edge auditor for statistical validation
    - Use: Validate edge across 6 datasets (2 TREND + 2 BALANCE per symbol)

  TRADE MODE (Sequential):
    - Executes single backtest with realistic trading simulation
    - Reports PnL, win rate, and execution quality
    - Use: Final validation before live deployment

WORKFLOW:
  1. Optimize params → cluster_optimizer.py
  2. Audit edge      → backtest_runner.py --mode audit --symbol LTCUSDT
  3. Validate trade  → backtest_runner.py --mode trade --symbol LTCUSDT
  4. Certify         → Merge to main + tag release

USAGE EXAMPLES:
  # Audit mode (default) - validates edge across all 6 datasets
  python scripts/backtest_runner.py --symbol LTCUSDT

  # Audit mode with filter (e.g., only 2024 datasets)
  python scripts/backtest_runner.py --symbol LTCUSDT --filter 2024

  # Trade mode - validates single most recent dataset
  python scripts/backtest_runner.py --mode trade --symbol LTCUSDT

  # Trade mode - validates specific dataset
  python scripts/backtest_runner.py --mode trade --dataset data/datasets/.../LTC_TREND_UP_2024-03.db

  # Cluster-wide audit (all symbols in MID_LIQUID cluster)
  python scripts/backtest_runner.py --protocol cluster_mid_liquid

===============================================================================
"""

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_python = os.path.join(_BASE, ".venv", "bin", "python")

_running = True


def handle_exit(signum, frame):
    global _running
    print("\n🛑 Signal received. Cancelling pending tasks...", flush=True)
    _running = False
    os._exit(1)


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


def set_low_priority():
    """Set nice=10 and ionice best-effort -n6 on worker processes."""
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        import subprocess

        subprocess.run(
            ["ionice", "-c2", "-n6", "-p", str(os.getpid())],
            capture_output=True,
            check=False,
        )
    except Exception:
        pass


def get_memory_status():
    """Return RAM + swap usage status string."""
    if not HAS_PSUTIL:
        return "N/A"
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return f"RAM: {mem.percent}% | Swap: {swap.percent}%"
    except Exception:
        return "N/A"


MAX_VISIBLE_LINES = 3


def redraw_progress(completed, total, pending_count, mem_status, elapsed, recent_lines):
    """Redraw spinner + last N completed tasks using ANSI escape codes."""
    # Move up and clear previous output
    lines_to_clear = min(len(recent_lines), MAX_VISIBLE_LINES)
    if lines_to_clear > 0:
        sys.stdout.write(f"\033[{lines_to_clear + 1}A")  # Move up
        sys.stdout.write("\033[2K" * (lines_to_clear + 1))  # Clear each line

    # Print last N completed tasks
    for line in recent_lines:
        sys.stdout.write(f"  {line}\n")

    # Print spinner line
    sys.stdout.write(
        f"\r⏳ [En progreso] {completed}/{total} completados | {pending_count} ejecutándose | {mem_status} | Transcurrido: {elapsed:.0f}s "
    )
    sys.stdout.flush()


DB_DIR = "data/datasets/daily_backtest_ready"
LOG_DIR = "logs"
TASK_TIMEOUT = 86400


def set_db_dir(new_db_dir: str) -> None:
    """Set the DB_DIR globally (used for --dataset-dir flag)."""
    global DB_DIR
    DB_DIR = new_db_dir


def _p(msg):
    """Print with immediate flush."""
    print(msg, flush=True)


def get_datasets_for_symbol(symbol, filter_pattern=None):
    pattern = f"*{symbol.replace('/USDT:USDT', '').replace('USDT', '')}*.db"
    files = glob.glob(os.path.join(DB_DIR, pattern))
    if filter_pattern:
        files = [f for f in files if filter_pattern in f]
    return [os.path.basename(f) for f in files]


def discover_all_symbols():
    files = glob.glob(os.path.join(DB_DIR, "*.db"))
    symbols = set()
    for f in files:
        name = os.path.basename(f).replace(".db", "")
        # Format: COINUSDT_REGIME_YYYY-MM-DD or LTC_REGIME_YYYY-MM-DD
        # Extract symbol prefix before first regime suffix
        for sep in ("_TREND_", "_BALANCE_"):
            idx = name.find(sep)
            if idx != -1:
                raw = name[:idx]
                sym = format_ccxt_symbol(raw)
                symbols.add(sym)
                break
    return sorted(symbols)


def pick_recent_dataset(symbol, filter_pattern=None):
    """Pick the most recent (by date) dataset for a symbol."""
    datasets = get_datasets_for_symbol(symbol, filter_pattern)
    if not datasets:
        return None

    def sort_key(name):
        base = name.replace(".db", "")
        parts = base.split("_")
        # LTC format: LTC_REGIME_YYYY-MM-DD → date is last part
        # Regular: YYYY-MM-DD_SYMUSDT → date is first part
        candidate = parts[0] if len(parts[0]) == 10 and parts[0][4] == "-" else parts[-1]
        try:
            return time.mktime(time.strptime(candidate, "%Y-%m-%d"))
        except (ValueError, IndexError):
            return 0

    datasets.sort(key=sort_key, reverse=True)
    return datasets[0]


def get_cluster_members(cluster_name):
    path = os.path.join(_BASE, "config", "clusters_fixed.json")
    with open(path) as f:
        data = json.load(f)
    for key, val in data["clusters"].items():
        if key.lower() == cluster_name.lower():
            return val.get("members", [])
    return []


def clean_temp_data():
    _p("🧹 Cleaning historian databases...")
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
    os.makedirs(LOG_DIR, exist_ok=True)


def format_ccxt_symbol(sym):
    if "/" in sym:
        return sym
    if sym.endswith("USDT"):
        base = sym[:-4]
        return f"{base}/USDT:USDT"
    # Bare ticker (e.g. LTC) → assume USDT pair
    return f"{sym}/USDT:USDT"


def run_backtest(task_config):
    if not _running:
        return False

    db_path = task_config["db_path"]
    symbol = task_config["symbol"]
    run_type = task_config["run_type"]
    task_id = task_config["task_id"]
    historian_db = f"data/historian_{task_id}.db"
    log_file = os.path.join(LOG_DIR, f"bt_{task_id}.log")

    cmd = [
        venv_python,
        "-u",
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

    try:
        with open(log_file, "w") as f:
            env = os.environ.copy()
            env["CASINO_HISTORIAN_DB"] = historian_db
            # Limitar hilos internos por subproceso para evitar saturación del host
            for var in [
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            ]:
                env[var] = "1"
            process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
            process.wait(timeout=TASK_TIMEOUT)
        return process.returncode == 0
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return False
    except Exception:
        return False


def build_tasks(mode, protocol_name, symbol, filter_pattern, dataset=None):
    """
    Build task list based on mode and protocol.

    AUDIT MODE:
      - single-coin-audit: 6 datasets (2 TREND_UP + 2 TREND_DOWN + 2 BALANCE)
      - cluster_*: All datasets for all symbols in cluster
      - trade-mode: Not available in audit mode

    TRADE MODE:
      - single-coin-audit: Most recent dataset only
      - trade-mode: Most recent or specific dataset
      - cluster_*: Not available in trade mode (one at a time)
    """
    tasks = []

    if mode == "audit":
        # ═══════════════════════════════════════════════════════════════
        # AUDIT MODE: Parallel execution across multiple datasets
        # Purpose: Statistical edge validation
        # ═══════════════════════════════════════════════════════════════
        if protocol_name.startswith("cluster_"):
            cluster_key = protocol_name[len("cluster_") :]
            members = get_cluster_members(cluster_key)
            for sym in members:
                datasets = get_datasets_for_symbol(sym, filter_pattern)
                for db_file in datasets:
                    tasks.append(
                        {
                            "task_id": db_file.replace(".db", ""),
                            "db_path": os.path.join(DB_DIR, db_file),
                            "symbol": format_ccxt_symbol(sym),
                            "run_type": "audit",
                        }
                    )
        elif protocol_name == "single-coin-audit":
            if not symbol:
                symbol = "LTCUSDT"
            datasets = get_datasets_for_symbol(symbol, filter_pattern)
            for db_file in datasets:
                tasks.append(
                    {
                        "task_id": db_file.replace(".db", ""),
                        "db_path": os.path.join(DB_DIR, db_file),
                        "symbol": format_ccxt_symbol(symbol),
                        "run_type": "audit",
                    }
                )
        elif protocol_name == "trade-mode":
            _p("❌ trade-mode not available in audit mode. Use --mode trade instead.")
            return []
    elif mode == "trade":
        # ═══════════════════════════════════════════════════════════════
        # TRADE MODE: Sequential execution, single dataset
        # Purpose: Realistic trading simulation before live deployment
        # REQUIRES: --dataset must be explicitly provided
        # ═══════════════════════════════════════════════════════════════
        if not dataset:
            _p("❌ TRADE MODE REQUIRES --dataset")
            _p("   Usage: python scripts/backtest_runner.py --mode trade --dataset <path_to_db>")
            _p(
                "   Example: python scripts/backtest_runner.py --mode trade --dataset data/datasets/daily_backtest_ready/LTC_TREND_UP_2024-03.db"
            )
            _p("\n   Available LTC datasets:")
            for db_file in sorted(glob.glob(os.path.join(DB_DIR, "LTC*.db"))):
                _p(f"     - {os.path.basename(db_file)}")
            return []

        if not os.path.exists(dataset):
            _p(f"❌ Dataset not found: {dataset}")
            return []

        db_file = os.path.basename(dataset)
        # Extract symbol from filename
        name = db_file.replace(".db", "")
        raw_sym = name
        for sep in ("_TREND_", "_BALANCE_", "_monthly_"):
            idx = name.find(sep)
            if idx != -1:
                raw_sym = name[:idx]
                break
        tasks.append(
            {
                "task_id": db_file.replace(".db", ""),
                "db_path": dataset,
                "symbol": format_ccxt_symbol(raw_sym),
                "run_type": "trade",
            }
        )

    return tasks


def calculate_workers(total_tasks):
    host_cores = os.cpu_count() or 4
    cpu_workers = max(1, int(host_cores * 0.65))

    if HAS_PSUTIL:
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            avail_ram_gb = mem.available / (1024**3)
            avail_swap_gb = swap.free / (1024**3)
            total_avail_gb = avail_ram_gb + avail_swap_gb
            mem_workers = max(1, int(total_avail_gb * 0.65 / 0.6))
        except Exception:
            mem_workers = cpu_workers
    else:
        mem_workers = cpu_workers

    safe_workers = min(cpu_workers, mem_workers)
    capped = min(safe_workers, total_tasks)
    return capped


def run_protocol(mode, protocol_name, symbol=None, filter_pattern=None, dataset=None):
    if not protocol_name:
        protocol_name = "single-coin-audit"

    if not clean_data_if_needed(mode, protocol_name):
        return

    tasks = build_tasks(mode, protocol_name, symbol, filter_pattern, dataset)
    if not tasks:
        _p("❌ No tasks to run. Check dataset availability.")
        return

    total = len(tasks)

    # Trade mode always runs sequentially (1 worker)
    actual_workers = 1 if mode == "trade" else calculate_workers(total)

    mode_label = "🔍 AUDIT" if mode == "audit" else "📊 TRADE"
    _p(
        f"\n🚀 {mode_label} MODE — {total} backtest(s), {actual_workers} worker(s) dinámicos (Host CPU: {os.cpu_count() or 4})\n"
    )

    completed = 0
    failed = 0
    start_time = time.time()
    recent_lines = deque(maxlen=MAX_VISIBLE_LINES)

    with ProcessPoolExecutor(max_workers=actual_workers, initializer=set_low_priority) as executor:
        future_map = {executor.submit(run_backtest, t): t for t in tasks}
        pending = set(future_map.keys())

        while pending and _running:
            # Esperamos 2 segundos máximo, para poder refrescar el progreso interactivamente
            done, pending = wait(pending, timeout=2.0, return_when=FIRST_COMPLETED)

            elapsed = time.time() - start_time
            mem_status = get_memory_status()

            for future in done:
                completed += 1
                t = future_map[future]
                task_id = t["task_id"]
                try:
                    ok = future.result()
                except Exception:
                    ok = False

                if not ok:
                    failed += 1

                icon = "✅" if ok else "❌"
                recent_lines.append(f"{icon} [{completed}/{total}] {task_id}")

            # Redraw with last 3 lines
            redraw_progress(completed, total, len(pending), mem_status, elapsed, recent_lines)

    # Limpiar línea final del progreso interactivo
    sys.stdout.write("\r" + " " * 110 + "\r")

    elapsed = time.time() - start_time
    _p(f"\n{'='*50}")
    _p(f"📊 {mode_label} MODE — {completed} done, {failed} failed, {elapsed:.0f}s")

    if failed == 0 and _running:
        if mode == "audit":
            # ═══════════════════════════════════════════════════════════════
            # POST-AUDIT PROCESSING (Audit mode only)
            # - Merge historian databases
            # - Run edge auditor
            # - Run L2 depth auditor
            # ═══════════════════════════════════════════════════════════════
            _p("\n🔗 Merging historian databases...")
            subprocess.run([venv_python, "utils/merge_historian.py"], check=True)
            _p("\n📊 Running edge auditor...")
            subprocess.run([venv_python, "utils/setup_edge_auditor.py", "--window", "21600"], check=True)
            _p("\n📊 Running L2 depth auditor...")
            subprocess.run([venv_python, "utils/l2_depth_auditor.py", "--db", "data/historian.db"], check=True)
            _p("\n✅ Audit mode complete.")
        else:
            # Trade mode: Just report final status
            _p("\n✅ Trade mode complete. Check logs/ for detailed PnL report.")
    elif failed > 0:
        _p(f"\n⚠️  {failed} backtest(s) failed. Check logs/ for details.")


def clean_data_if_needed(mode, protocol_name):
    """Clean temp data only for audit mode (not for trade mode)."""
    if mode == "audit" and protocol_name != "trade-mode":
        clean_temp_data()
    else:
        os.makedirs(LOG_DIR, exist_ok=True)
    return True


if __name__ == "__main__":
    epilog = """
═══════════════════════════════════════════════════════════════════════════
MODES OF OPERATION
═══════════════════════════════════════════════════════════════════════════

🔍 AUDIT MODE (Default):
    Executes multiple backtests in parallel, merges results, and runs
    statistical edge analysis. Use for validating edge across datasets.

    Examples:
      # Audit all 6 datasets for a symbol (2 TREND + 2 BALANCE)
      python scripts/backtest_runner.py --mode audit --symbol LTCUSDT

      # Audit with year filter
      python scripts/backtest_runner.py --mode audit --symbol LTCUSDT --filter 2024

      # Audit entire cluster (all symbols)
      python scripts/backtest_runner.py --mode audit --protocol cluster_mid_liquid

      # Audit monthly datasets (point to monthly dir)
      python scripts/backtest_runner.py --mode audit --symbol LTCUSDT --dataset-dir data/datasets/monthly_backtest_ready

📊 TRADE MODE:
   Executes single backtest with realistic trading simulation. Use for
   final validation before live deployment.

   Examples:
     # Trade most recent dataset
     python scripts/backtest_runner.py --mode trade --symbol LTCUSDT

     # Trade specific dataset
     python scripts/backtest_runner.py --mode trade --dataset data/datasets/.../LTC_TREND_UP_2024-03.db

═══════════════════════════════════════════════════════════════════════════
RECOMMENDED WORKFLOW
═══════════════════════════════════════════════════════════════════════════

1. Optimize parameters:
   python scripts/cluster_optimizer.py --cluster LTC_NOISY_UNCERTAIN_1 --iterations 50

2. Audit edge (statistical validation):
   python scripts/backtest_runner.py --mode audit --symbol LTCUSDT
   → Look for: Net Taker > 0, all scenarios "TARGETS OK"

3. Validate trade (realistic simulation):
   python scripts/backtest_runner.py --mode trade --symbol LTCUSDT
   → Look for: Positive PnL, acceptable win rate

4. Certify and deploy:
   # After successful audit + trade validation, merge to main branch
"""

    parser = argparse.ArgumentParser(
        prog="backtest_runner",
        description="🎯 Unified Backtest Execution Engine — Audit edge statistically or validate in trade simulation",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["audit", "trade"],
        default="audit",
        help="Execution mode: 'audit' for parallel statistical validation (default), 'trade' for sequential realistic simulation",
    )
    parser.add_argument(
        "--protocol",
        default=None,
        help="Protocol to run: 'single-coin-audit' (default), 'cluster_<name>', or 'trade-mode' (auto-detected in trade mode)",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Symbol to test (e.g., LTCUSDT, SOLUSDT). Required for single-coin-audit. Optional for trade-mode if using --dataset.",
    )
    parser.add_argument(
        "--filter",
        default=None,
        help="Filter datasets by date pattern (e.g., 2024, 2025-03). Uses substring match on filename.",
    )
    parser.add_argument(
        "--dataset",
        required=False,
        default=None,
        help="Exact path to a .db file. REQUIRED for trade mode. Useful for testing specific datasets in audit mode.",
    )
    parser.add_argument(
        "--dataset-dir",
        required=False,
        default=None,
        help="Custom dataset directory. Default: data/datasets/daily_backtest_ready. Use --dataset-dir data/datasets/monthly_backtest_ready for monthly datasets.",
    )
    args = parser.parse_args()

    # Set custom dataset directory if provided
    if args.dataset_dir:
        set_db_dir(args.dataset_dir)

    # Auto-detect protocol if not specified
    protocol = args.protocol
    if not protocol:
        protocol = "trade-mode" if args.mode == "trade" else "single-coin-audit"

    try:
        run_protocol(args.mode, protocol, args.symbol, args.filter, args.dataset)
    except Exception as e:
        _p(f"\n❌ FATAL: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
