import argparse
import glob
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor

# Configuration for protocols
PROTOCOLS = {
    "generalized": {
        "assets": [
            "LTCUSDT",
            "XRPUSDT",
            "DOGEUSDT",
            "LINKUSDT",
            "ADAUSDT",
            "SUIUSDT",
            "BNBUSDT",
            "AVAXUSDT",
            "ETHUSDT",
            "SOLUSDT",
        ],
        "max_workers": 4,
    },
    "long-range": {"assets": ["LTCUSDT"], "max_workers": 3},
    "single-coin": {"max_workers": 1},
}


def clean_temp_data():
    print("Cleaning temporary historian databases...")
    for f in glob.glob("data/historian_*.db"):
        os.remove(f)


def run_single_backtest(asset):
    # If dataset path pattern depends on asset
    db_path = f"data/datasets/backtest_ready/2024-01-01_{asset}.db"
    historian_db = f"data/historian_{asset}.db"

    print(f"Starting backtest for {asset}")
    cmd = [
        "./.venv/bin/python",
        "backtest.py",
        "--depth-db-path",
        db_path,
        "--symbol",
        asset,
        "--historian-db",
        historian_db,
        "--audit",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running backtest for {asset}: {result.stderr}")
        return False
    print(f"Finished backtest for {asset}")
    return True


def run_protocol(protocol_name, symbol=None):
    clean_temp_data()
    print(f"Starting protocol: {protocol_name}")

    if protocol_name == "single-coin":
        assets = [symbol] if symbol else ["LTCUSDT"]
        results = [run_single_backtest(assets[0])]
    else:
        config = PROTOCOLS[protocol_name]
        with ProcessPoolExecutor(max_workers=config["max_workers"]) as executor:
            results = list(executor.map(run_single_backtest, config["assets"]))

    if all(results):
        print(f"All backtests for {protocol_name} complete. Merging...")
        subprocess.run(["python", "utils/merge_historian.py"])
        print("Running exit edge auditor...")
        subprocess.run(["python", "utils/exit_edge_auditor.py"])
        print("Protocol complete.")
    else:
        print("Some backtests failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestrator for audit protocols")
    parser.add_argument("--protocol", choices=PROTOCOLS.keys(), required=True)
    parser.add_argument("--symbol", help="Symbol for single-coin audit")
    args = parser.parse_args()

    run_protocol(args.protocol, args.symbol)
