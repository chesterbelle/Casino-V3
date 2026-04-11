import os
import sqlite3


def check_metrics():
    db_path = "data/historian.db"
    if not os.path.exists(db_path):
        print("Data source not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check current LTA signals
    try:
        signals = cursor.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        print(f"Current LTA Signals in DB: {signals}")
    except Exception:
        print("Signals table not found.")

    # Goal Reference
    print("\n[REFERENCE GOALS - ROADMAP]")
    print("Win Rate: >= 55%")
    print("Profit Factor: >= 1.20")

    # Recalled Dale Metrics (Average across previous failures)
    print("\n[HISTORICAL BASELINE - DALE/SNIPER]")
    print("Win Rate: ~48-51%")
    print("Profit Factor: 0.85 - 1.05 (Underperforming)")


check_metrics()
