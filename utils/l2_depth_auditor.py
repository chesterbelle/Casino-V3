import argparse
import json
import math
import os
import sqlite3
import time

HISTORIAN_DB = "data/historian.db"
DATASETS_DIR = "data/datasets/daily_backtest_ready"

AMT_SCENARIOS = ["tactical_absorption", "trend_acceptance", "liquidity_exhaustion", "failed_breakout"]

# ANSI Colors
CYAN = "\033[96m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# Cache: (dataset_path, min_ts, max_ts)
_depth_cache = {}


def _find_dataset_for_ts(symbol, target_ts):
    """Find dataset file whose depth_snapshot timestamps bracket target_ts."""
    base_asset = symbol.split("/")[0]
    for f in os.listdir(DATASETS_DIR):
        if base_asset not in f or not f.endswith(".db"):
            continue
        path = os.path.join(DATASETS_DIR, f)

        if path in _depth_cache:
            lo, hi = _depth_cache[path]
        else:
            try:
                conn = sqlite3.connect(path)
                row = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM depth_snapshots").fetchone()
                conn.close()
            except Exception:
                continue
            if row[0] is None:
                _depth_cache[path] = (None, None)
                continue
            lo, hi = row
            _depth_cache[path] = (lo, hi)

        if lo is not None and lo <= target_ts <= hi:
            return path
    return None


def get_depth_snapshot(symbol, target_ts):
    dataset_file = _find_dataset_for_ts(symbol, target_ts)
    if not dataset_file:
        return None, None

    conn = sqlite3.connect(dataset_file)
    try:
        row = conn.execute(
            "SELECT bids, asks FROM depth_snapshots WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
            (target_ts,),
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


def audit_by_scenario(hist_conn, rows, scenario_name):
    signals = []
    for sym, ts, side, price, meta_str in rows:
        try:
            meta = json.loads(meta_str) if meta_str else {}
        except Exception:
            meta = {}
        if meta.get("scenario") == scenario_name:
            signals.append((sym, ts, side, price, meta_str))

    if not signals:
        print(f"   {YELLOW}⚠️  0 signals found for '{scenario_name}'{RESET}")
        return

    results = {
        "High Wall (>2.0)": {"mfe": [], "mae": []},
        "Balanced (1.0-2.0)": {"mfe": [], "mae": []},
        "Thin Wall (<1.0)": {"mfe": [], "mae": []},
    }

    for sym, ts, side, price, meta_str in signals:
        bids, asks = get_depth_snapshot(sym, ts)
        if not bids or not asks:
            continue
        ratio = calculate_l2_ratio(bids, asks, price, side)
        mfe, mae = calculate_mfe_mae(hist_conn, sym, ts, price, side)
        if ratio >= 2.0:
            cat = "High Wall (>2.0)"
        elif ratio >= 1.0:
            cat = "Balanced (1.0-2.0)"
        else:
            cat = "Thin Wall (<1.0)"
        results[cat]["mfe"].append(mfe)
        results[cat]["mae"].append(mae)

    print(f"\n  {BOLD}{scenario_name}{RESET} ({len(signals)} signals)")
    print(f"  {'L2 RATIO (Wall)':<20} | {'n':<6} | {'AVG MFE%':<10} | {'AVG MAE%':<10} | {'RATIO':<8}")
    print(f"  {'-'*60}")
    for cat, data in results.items():
        n = len(data["mfe"])
        if n == 0:
            continue
        avg_mfe = sum(data["mfe"]) / n * 100
        avg_mae = sum(data["mae"]) / n * 100
        mfe_mae_ratio = abs(avg_mfe / avg_mae) if avg_mae != 0 else 0
        color = GREEN if mfe_mae_ratio > 1.2 else (RED if mfe_mae_ratio < 0.9 else YELLOW)
        print(f"  {cat:<20} | {n:<6} | {avg_mfe:>8.3f}% | {avg_mae:>8.3f}% | {color}{mfe_mae_ratio:>7.2f}{RESET}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/historian.db", help="Path to historian DB")
    args = parser.parse_args()

    print("=" * 70)
    print(" L2 DEPTH AUDITOR — All AMT Scenarios")
    print("=" * 70)

    if not os.path.exists(args.db):
        print(f"{RED}❌ Database not found: {args.db}{RESET}")
        print("Run a backtest with --audit first.")
        return

    hist_conn = sqlite3.connect(args.db)

    rows = hist_conn.execute("SELECT symbol, timestamp, side, price, metadata FROM signals").fetchall()

    print(f"[*] Total signals in DB: {len(rows)}")
    print(f"[*] Correlating with L2 Depth for each AMT scenario...\n")

    for scenario in AMT_SCENARIOS:
        audit_by_scenario(hist_conn, rows, scenario)

    print(f"\n{'='*70}")
    print("[HYPOTHESIS CHECK]")
    print("If 'High Wall' has a significantly better MFE/MAE Ratio (>1.2) than 'Thin Wall',")
    print("it proves that requiring L2 passive support is a mandatory structural edge.")
    print(f"{'='*70}")

    hist_conn.close()


if __name__ == "__main__":
    main()
