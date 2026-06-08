import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

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


PROTOCOLS = {
    "generalized": {"run_type": "audit", "max_workers": 2, "skip_merge": False},
    "cluster_mid_liquid": {"run_type": "audit", "max_workers": 2, "skip_merge": False},
    "cluster_mega_liquid": {"run_type": "audit", "max_workers": 2, "skip_merge": False},
    "cluster_major_liquid": {"run_type": "audit", "max_workers": 2, "skip_merge": False},
    "cluster_thin_volatile": {"run_type": "audit", "max_workers": 2, "skip_merge": False},
    "cluster_illiqid_spec": {"run_type": "audit", "max_workers": 2, "skip_merge": False},
    "single-coin": {"run_type": "audit", "max_workers": 2, "skip_merge": True, "skip_clean": True},
    "strategy": {"run_type": "trade", "max_workers": 1, "skip_merge": True},
}

DB_DIR = "data/datasets/backtest_ready"
LOG_DIR = "logs"
TASK_TIMEOUT = 86400


def _p(msg):
    """Print with immediate flush."""
    print(msg, flush=True)


def get_datasets_for_symbol(symbol, filter_pattern=None):
    pattern = f"*{symbol.replace('/USDT:USDT', '').replace('USDT', '')}*.db"
    files = glob.glob(os.path.join(DB_DIR, pattern))
    if filter_pattern:
        files = [f for f in files if filter_pattern in f]
    return [os.path.basename(f) for f in files]


def get_cluster_protocol(cluster_name):
    with open("config/clusters_fixed.json") as f:
        data = json.load(f)
    return data["clusters"].get(cluster_name, {}).get("members", [])


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
    return sym


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


def build_tasks(protocol_name, symbol, filter_pattern):
    config = PROTOCOLS.get(protocol_name)
    tasks = []

    if protocol_name.startswith("cluster_"):
        cluster_key = protocol_name.replace("cluster_", "").upper()
        members = get_cluster_protocol(cluster_key)
        for sym in members:
            datasets = get_datasets_for_symbol(sym, filter_pattern)
            for db_file in datasets:
                tasks.append(
                    {
                        "task_id": db_file.replace(".db", ""),
                        "db_path": os.path.join(DB_DIR, db_file),
                        "symbol": format_ccxt_symbol(sym),
                        "run_type": config["run_type"],
                    }
                )
    elif protocol_name == "single-coin":
        if not symbol:
            symbol = "LTCUSDT"
        datasets = get_datasets_for_symbol(symbol, filter_pattern)
        for db_file in datasets:
            tasks.append(
                {
                    "task_id": db_file.replace(".db", ""),
                    "db_path": os.path.join(DB_DIR, db_file),
                    "symbol": format_ccxt_symbol(symbol),
                    "run_type": config["run_type"],
                }
            )
    elif "datasets" in config:
        for db_file in config["datasets"]:
            path = os.path.join(DB_DIR, db_file)
            if not os.path.exists(path):
                _p(f"  ⚠️ Missing: {path}")
                continue
            tasks.append(
                {
                    "task_id": db_file.replace(".db", ""),
                    "db_path": path,
                    "symbol": config.get("symbol", format_ccxt_symbol(db_file)),
                    "run_type": config["run_type"],
                }
            )
    else:
        _p(f"❌ Unknown protocol type: {protocol_name}")

    return tasks


def run_protocol(protocol_name, symbol=None, filter_pattern=None):
    config = PROTOCOLS.get(protocol_name)
    if not config:
        _p(f"❌ Unknown protocol: {protocol_name}")
        return

    if not config.get("skip_clean", False):
        clean_temp_data()
    else:
        os.makedirs(LOG_DIR, exist_ok=True)

    tasks = build_tasks(protocol_name, symbol, filter_pattern)
    if not tasks:
        _p("❌ No tasks to run. Check dataset availability.")
        return

    total = len(tasks)

    # Cálculo dinámico de workers para no saturar el host (parecido a un semáforo)
    host_cores = os.cpu_count() or 4
    # Dejamos 2 cores libres para el sistema, pero usamos al menos 1
    safe_workers = max(1, host_cores - 8)
    # Si el protocolo pide menos, lo respetamos (por ej. estrategia), si no usamos la capacidad segura
    protocol_workers = config.get("max_workers", 2)
    actual_workers = max(protocol_workers, safe_workers)
    actual_workers = min(total, actual_workers)

    _p(
        f"\n🚀 {protocol_name.upper()} — {total} backtests, {actual_workers} workers dinámicos (Host CPU: {host_cores})\n"
    )

    completed = 0
    failed = 0
    start_time = time.time()

    with ProcessPoolExecutor(max_workers=actual_workers) as executor:
        future_map = {executor.submit(run_backtest, t): t for t in tasks}
        pending = set(future_map.keys())

        while pending and _running:
            # Esperamos 2 segundos máximo, para poder refrescar el progreso interactivamente
            done, pending = wait(pending, timeout=2.0, return_when=FIRST_COMPLETED)

            elapsed = time.time() - start_time
            rate = completed / elapsed if elapsed > 0 else 0
            remaining = (total - completed) / rate if rate > 0 else 0

            # Spinner interactivo actualizándose sin nueva línea
            sys.stdout.write(
                f"\r⏳ [En progreso] {completed}/{total} completados | {len(pending)} ejecutándose | Transcurrido: {elapsed:.0f}s | ETA: ~{remaining:.0f}s "
            )
            sys.stdout.flush()

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
                # Limpiar línea del spinner y printear el completado
                sys.stdout.write("\r" + " " * 110 + "\r")
                _p(f"  {icon} [{completed}/{total}] {task_id}")

    # Limpiar línea final del progreso interactivo
    sys.stdout.write("\r" + " " * 110 + "\r")

    elapsed = time.time() - start_time
    _p(f"\n{'='*50}")
    _p(f"📊 {protocol_name.upper()} — {completed} done, {failed} failed, {elapsed:.0f}s")

    if failed == 0 and _running:
        skip_merge = config.get("skip_merge", False)
        if config["run_type"] == "audit" and not skip_merge:
            _p("\n🔗 Merging historian databases...")
            subprocess.run([venv_python, "utils/merge_historian.py"], check=True)
            _p("\n📊 Running edge auditor...")
            subprocess.run([venv_python, "utils/setup_edge_auditor.py", "--window", "21600"], check=True)
            _p("\n📊 Running L2 depth auditor...")
            subprocess.run([venv_python, "utils/l2_depth_auditor.py", "--db", "data/historian.db"], check=True)
        _p("\n✅ Protocol complete.")
    elif failed > 0:
        _p(f"\n⚠️  {failed} backtest(s) failed. Check logs/ for details.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Orchestrator for Casino-V3")
    parser.add_argument("--protocol", choices=PROTOCOLS.keys(), required=True)
    parser.add_argument("--symbol", help="Symbol for single-coin")
    parser.add_argument("--filter", help="Filter pattern for datasets (e.g. 2025)")
    args = parser.parse_args()

    try:
        run_protocol(args.protocol, args.symbol, args.filter)
    except Exception as e:
        _p(f"\n❌ FATAL: {e}")
        sys.exit(1)
