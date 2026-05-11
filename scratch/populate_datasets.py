import os
import shutil
import subprocess

# Configuración de fechas y regímenes
datasets = {
    "LTC": {
        "RANGE": ["2024-02-01", "2024-05-01", "2024-08-01"],
        "BEAR": ["2024-04-01", "2024-10-01", "2025-02-01"],
        "BULL": ["2024-03-01", "2024-12-01", "2025-05-01"],
    },
    "DOGE": {
        "RANGE": ["2024-02-01", "2024-06-01", "2024-11-01"],
        "BEAR": ["2024-04-01", "2024-09-01", "2025-02-01"],
        "BULL": ["2024-03-01", "2025-01-01", "2025-05-01"],
    },
}

base_dir = "/home/chesterbelle/Casino-V3"
certified_dir = f"{base_dir}/data/datasets/certified"
ready_dir = f"{base_dir}/data/datasets/backtest_ready"

os.makedirs(certified_dir, exist_ok=True)


def run_cmd(cmd):
    print(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    return result.returncode == 0


for symbol, regimes in datasets.items():
    binance_sym = symbol + "USDT"
    for regime, dates in regimes.items():
        for date in dates:
            print(f"\n--- Processing {symbol} {regime} ({date}) ---")

            # 1. Download
            fetch_cmd = f".venv/bin/python utils/data/tardis_fetcher.py --symbol {binance_sym} --start {date}"
            if not run_cmd(fetch_cmd):
                continue

            # 2. Process
            # Note: processor expects name like '2024-02-01_LTCUSDT'
            name_pattern = f"{date}_{binance_sym}"
            process_cmd = f".venv/bin/python utils/data/l2_processor.py --name {name_pattern} --symbol {binance_sym}"
            if not run_cmd(process_cmd):
                continue

            # 3. Rename and Move
            source_db = f"{ready_dir}/{name_pattern}.db"
            target_db = f"{certified_dir}/{symbol}_{regime}_{date}.db"

            if os.path.exists(source_db):
                shutil.move(source_db, target_db)
                print(f"✅ Success: {target_db}")
            else:
                print(f"❌ Error: {source_db} not found")

print("\n🚀 All datasets processed and moved to data/datasets/certified/")
