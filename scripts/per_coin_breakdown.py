import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils"))
from setup_edge_auditor import EdgeAuditor  # noqa: E402


def run_breakdown():
    db_path = "data/historian.db"
    if not os.path.exists(db_path):
        print("Historian DB not found.")
        return

    auditor = EdgeAuditor(db_path)
    signals, prices, _ = auditor.load_data()

    symbols = signals["symbol"].unique()

    print(f"{'Symbol':<15} | {'Signals':<10} | {'Net Taker':<12} | {'WR%':<8} | {'Verdict'}")
    print("-" * 60)

    for sym in symbols:
        pass


run_breakdown()
