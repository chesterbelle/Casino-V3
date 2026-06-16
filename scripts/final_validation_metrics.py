import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils"))
from setup_edge_auditor import EdgeAuditor  # noqa: E402


def get_metrics(db_path):
    try:
        auditor = EdgeAuditor(db_path)
        return auditor.get_metrics()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    dbs = {"XRP": "data/histan_final_val_xrp.db", "DOGE": "data/histan_final_val_doge.db"}

    for coin, path in dbs.items():
        if os.path.exists(path):
            print(f"--- {coin} ---")
            print(get_metrics(path))
        else:
            print(f"--- {coin} --- File not found: {path}")
