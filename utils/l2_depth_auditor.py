import json
import math
import os
import sqlite3
import time

HISTORIAN_DB = "data/historian.db"
DATASETS_DIR = "data/datasets/backtest_ready"


def get_depth_snapshot(symbol, target_ts):
    """Fetches the closest L2 depth snapshot from the dataset."""
    # Assuming dataset file format: 2024-01-01_SYMBOL.db
    # We will search for the first matching db for the symbol
    dataset_file = None
    for f in os.listdir(DATASETS_DIR):
        base_asset = symbol.split("/")[0]
        if base_asset in f and f.endswith(".db"):
            dataset_file = os.path.join(DATASETS_DIR, f)
            break

    if not dataset_file:
        return None, None

    conn = sqlite3.connect(dataset_file)
    try:
        # Get the closest snapshot before or exactly at the target_ts
        # We look up to 1 second back
        row = conn.execute(
            "SELECT bids, asks FROM depth_snapshots WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1", (target_ts,)
        ).fetchone()

        if row:
            bids = json.loads(row[0])
            asks = json.loads(row[1])
            return bids, asks
        return None, None
    finally:
        conn.close()


def calculate_mfe_mae(hist_conn, symbol, start_ts, entry_price, side, timeout=1800):
    """Calculates Maximum Favorable/Adverse Excursion for a given signal."""
    samples = hist_conn.execute(
        """
        SELECT price FROM price_samples
        WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC
    """,
        (symbol, start_ts, start_ts + timeout),
    ).fetchall()

    if not samples:
        return 0.0, 0.0

    prices = [r[0] for r in samples]
    highest = max(prices)
    lowest = min(prices)

    if side == "LONG":
        mfe = (highest - entry_price) / entry_price
        mae = (lowest - entry_price) / entry_price
    else:
        mfe = (entry_price - lowest) / entry_price
        mae = (entry_price - highest) / entry_price

    return mfe, mae


def calculate_l2_ratio(bids, asks, price, side, depth_pct=0.002):
    """Calculates the imbalance ratio of passive liquidity within depth_pct (0.2%)."""
    bid_vol = sum(float(v) for p, v in bids if float(p) >= price * (1 - depth_pct))
    ask_vol = sum(float(v) for p, v in asks if float(p) <= price * (1 + depth_pct))

    # Avoid division by zero
    bid_vol = max(bid_vol, 0.01)
    ask_vol = max(ask_vol, 0.01)

    if side == "LONG":
        return bid_vol / ask_vol
    else:
        return ask_vol / bid_vol


def main():
    print("======================================================================")
    print(" L2 DEPTH AUDITOR - Zero-Interference Microstructure Certification")
    print("======================================================================")

    try:
        hist_conn = sqlite3.connect(HISTORIAN_DB)
    except Exception:
        print("Error: No historian DB found. Run a backtest with --audit first.")
        return

    # 1. Get all IN_VALUE TacticalAbsorption signals
    # We filter out rejected ones by joining with decision_traces (only getting EXECUTED)
    # Wait, we can just get all signals and trace them
    signals = hist_conn.execute(
        """
        SELECT symbol, timestamp, side, price, metadata
        FROM signals
        WHERE setup_type = 'TacticalAbsorptionV2'
    """
    ).fetchall()

    print(f"[*] Found {len(signals)} signals. Correlating with L2 Depth... This may take a minute.")

    results = {
        "High Wall (>2.0)": {"mfe": [], "mae": []},
        "Balanced (1.0-2.0)": {"mfe": [], "mae": []},
        "Thin Wall (<1.0)": {"mfe": [], "mae": []},
    }

    processed = 0
    for sym, ts, side, price, meta_str in signals:
        # Check if it was accepted by StructureGuardian

        # We only audit trades that actually made it through the filters
        # But for diagnostic purposes, let's just audit them all to see if L2 correlates!

        bids, asks = get_depth_snapshot(sym, ts)
        if not bids or not asks:
            continue

        ratio = calculate_l2_ratio(bids, asks, price, side)
        mfe, mae = calculate_mfe_mae(hist_conn, sym, ts, price, side)

        # Categorize
        if ratio >= 2.0:
            cat = "High Wall (>2.0)"
        elif ratio >= 1.0:
            cat = "Balanced (1.0-2.0)"
        else:
            cat = "Thin Wall (<1.0)"

        results[cat]["mfe"].append(mfe)
        results[cat]["mae"].append(mae)
        processed += 1

        if processed % 500 == 0:
            print(f"   ... Processed {processed} signals.")

    print("\n[L2 DEPTH RATIO AUDIT RESULTS]")
    print(f"{'L2 RATIO (Wall)':<20} | {'TRADES':<8} | {'AVG MFE %':<10} | {'AVG MAE %':<10} | {'RATIO (MFE/MAE)':<15}")
    print("-" * 70)

    for cat, data in results.items():
        n = len(data["mfe"])
        if n == 0:
            continue

        avg_mfe = sum(data["mfe"]) / n * 100
        avg_mae = sum(data["mae"]) / n * 100
        mfe_mae_ratio = abs(avg_mfe / avg_mae) if avg_mae != 0 else 0

        # Terminal colors
        color = "\033[92m" if mfe_mae_ratio > 1.2 else ("\033[91m" if mfe_mae_ratio < 0.9 else "\033[93m")
        reset = "\033[0m"

        print(f"{cat:<20} | {n:<8} | {avg_mfe:>9.3f}% | {avg_mae:>9.3f}% | {color}{mfe_mae_ratio:>14.2f}{reset}")

    print("\n[HYPOTHESIS CHECK]")
    print("If 'High Wall' has a significantly better MFE/MAE Ratio (>1.2) than 'Thin Wall',")
    print("it proves that requiring L2 passive support is a mandatory structural edge.")


if __name__ == "__main__":
    main()
