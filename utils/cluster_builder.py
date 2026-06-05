#!/usr/bin/env python3
"""
Cluster Builder — Offline Clustering Pipeline (Institutional 5 Dimensions)
Reads microstructure data from raw datasets in data/datasets/backtest_ready/
"""
import argparse
import collections
import glob
import json
import math
import random
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, ".")

CLUSTERS_PATH = Path("config/clusters.json")

NORM_MIN = {
    "tick_size_efficiency": 0.0,
    "book_density": 0.0,
    "volume_vol_ratio": 0.0,
    "speed": 0.0,
    "micro_volatility": 0.0,
}
NORM_MAX = {
    "tick_size_efficiency": 1.0,
    "book_density": 25.0,
    "volume_vol_ratio": 18.0,
    "speed": 500.0,
    "micro_volatility": 1.0,
}


def _euclidean_distance(a: dict, b: dict) -> float:
    keys = set(a.keys()) & set(b.keys())
    if not keys:
        return float("inf")
    return math.sqrt(sum((a.get(k, 0) - b.get(k, 0)) ** 2 for k in keys))


def _normalize(metrics: dict, norm_min: dict, norm_max: dict, skip_log1p: bool = False) -> dict:
    normalized = {}
    for key, value in metrics.items():
        if value is None:
            normalized[key] = 0.5
            continue
        if not skip_log1p and key in ("book_density", "volume_vol_ratio") and value > 0:
            value = math.log1p(value)
        min_val = norm_min.get(key, 0)
        max_val = norm_max.get(key, 1)
        if max_val <= min_val:
            normalized[key] = 0.5
            continue
        normalized[key] = max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
    return normalized


def _compute_metrics_from_dataset(conn: sqlite3.Connection, symbol: str) -> Optional[Dict]:
    """Compute 5 dimensions from a single dataset file."""
    try:
        # 1. Tick Size Efficiency (from market_trades)
        efficiency = None
        trades_row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END) FROM market_trades WHERE symbol=?", (symbol,)
        ).fetchone()
        if trades_row and trades_row[0] and trades_row[0] > 10:
            total, buys = trades_row
            efficiency = 1.0 - abs((buys - (total - buys)) / total) if total > 0 else None

        # 2. Book Density (TWA from depth_snapshots)
        density = None
        depth_rows = conn.execute(
            "SELECT bids, asks FROM depth_snapshots WHERE symbol=? ORDER BY timestamp DESC LIMIT 20", (symbol,)
        ).fetchall()
        if depth_rows:
            densities = []
            for bids_raw, asks_raw in depth_rows:
                bids = json.loads(bids_raw) if isinstance(bids_raw, str) else bids_raw
                asks = json.loads(asks_raw) if isinstance(asks_raw, str) else asks_raw
                if bids and asks:
                    try:
                        bp, ap = float(bids[0][0]), float(asks[0][0])
                        mid = (bp + ap) / 2
                        spread_pct = (ap - bp) / mid if mid > 0 else 0.001
                        vol = sum(float(l[1]) for l in bids) + sum(float(l[1]) for l in asks)
                        densities.append(vol / spread_pct if spread_pct > 0 else 0)
                    except (IndexError, ValueError, TypeError):
                        continue
            if densities:
                density = sum(densities) / len(densities)

        # 3. Speed
        speed = None
        t_row = conn.execute(
            "SELECT COUNT(*), MAX(timestamp)-MIN(timestamp) FROM market_trades WHERE symbol=?", (symbol,)
        ).fetchone()
        if t_row and t_row[1] and float(t_row[1]) > 0:
            speed = t_row[0] / float(t_row[1])

        # 4. Volume/Vol Ratio
        vol_ratio = None
        p_rows = conn.execute(
            "SELECT close FROM price_candles WHERE symbol=? ORDER BY timestamp DESC LIMIT 14400", (symbol,)
        ).fetchall()
        prices = [float(r[0]) for r in p_rows if r[0] and float(r[0]) > 0]
        if len(prices) >= 50:
            log_rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
            if log_rets:
                mean = sum(log_rets) / len(log_rets)
                vol = math.sqrt(sum((r - mean) ** 2 for r in log_rets) / len(log_rets))
                if vol > 0:
                    res_vol = conn.execute(
                        "SELECT SUM(price * amount) FROM market_trades WHERE symbol=?", (symbol,)
                    ).fetchone()
                    total_usd = res_vol[0] if res_vol and res_vol[0] else 0
                    vol_ratio = total_usd / (vol * 1e6)

        # 5. Micro Volatility
        micro_vol = None
        if len(prices) >= 20:
            rets = [abs(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0]
            if rets:
                micro_vol = sum(rets) / len(rets)

        return {
            "tick_size_efficiency": efficiency,
            "book_density": density,
            "volume_vol_ratio": vol_ratio,
            "speed": speed,
            "micro_volatility": micro_vol,
        }
    except Exception as e:
        print(f"  ⚠️ Error in {symbol}: {e}")
        return None


def kmeans(data: List[Dict], k: int, max_iter: int = 100, seed: int = 42) -> Tuple[List[Dict], List[int]]:
    random.seed(seed)
    dims = list(data[0].keys())
    n = len(data)
    centroids = [dict(data[random.randint(0, n - 1)])]
    for _ in range(1, k):
        distances = [min(_euclidean_distance(point, c) for c in centroids) for point in data]
        total = sum(distances)
        if total <= 0:
            centroids.append(dict(data[random.randint(0, n - 1)]))
            continue
        probs = [d / total for d in distances]
        cumulative, found = 0, False
        for i, p in enumerate(probs):
            cumulative += p
            if random.random() <= cumulative:
                centroids.append(dict(data[i]))
                found = True
                break
        if not found:
            centroids.append(dict(data[-1]))

    assignments = [0] * n
    for _ in range(max_iter):
        new_assignments = []
        for point in data:
            dists = [_euclidean_distance(point, c) for c in centroids]
            new_assignments.append(dists.index(min(dists)))
        if new_assignments == assignments:
            break
        assignments = new_assignments
        for c_idx in range(k):
            members = [data[i] for i in range(n) if assignments[i] == c_idx]
            if not members:
                continue
            for dim in dims:
                vals = [m[dim] for m in members if dim in m]
                centroids[c_idx][dim] = sum(vals) / len(vals) if vals else 0
    return centroids, assignments


def compute_silhouette(data: List[Dict], assignments: List[int], centroids: List[Dict]) -> float:
    if len(data) < 2:
        return 0.0
    total = 0
    for i, point in enumerate(data):
        my_cluster = assignments[i]
        same = [data[j] for j in range(len(data)) if assignments[j] == my_cluster and j != i]
        a = sum(_euclidean_distance(point, s) for s in same) / len(same) if same else 0
        b = float("inf")
        for c_idx in set(assignments):
            if c_idx == my_cluster:
                continue
            others = [data[j] for j in range(len(data)) if assignments[j] == c_idx]
            if others:
                b = min(b, sum(_euclidean_distance(point, o) for o in others) / len(others))
        if b == float("inf"):
            continue
        total += (b - a) / max(a, b) if max(a, b) > 0 else 0
    return total / len(data) if data else 0


def _generate_cluster_names(k: int) -> List[str]:
    return ["MEGA_LIQUID", "MAJOR_LIQUID", "MID_LIQUID", "THIN_VOLATILE", "ILLIQUID_SPEC", "C6", "C7", "C8"][:k]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_dir", default="data/datasets/backtest_ready/", help="Directory with .db datasets")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", default="config/clusters_fixed.json")
    args = parser.parse_args()

    print(f"\n{'═'*65}\n  BUILDING CLUSTERS FROM DATASETS (k={args.k})\n{'═'*65}")

    files = glob.glob(f"{args.dataset_dir}/*.db")
    symbol_metrics = collections.defaultdict(list)

    for f in files:
        name = Path(f).stem
        if "_" in name:
            sym = name.split("_")[0] if not name[0].isdigit() else name.split("_")[1]
        else:
            sym = name

        # Normalize symbol to match DB (e.g., LTC -> LTCUSDT)
        db_sym = sym
        conn = sqlite3.connect(f)
        # Check what symbols actually exist in this DB
        actual_symbols = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM market_trades").fetchall()]
        if not actual_symbols:
            # Try price_candles if market_trades is empty
            actual_symbols = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM price_candles").fetchall()]

        if actual_symbols:
            # Find the best match among actual symbols
            for s in actual_symbols:
                if s.startswith(sym):
                    db_sym = s
                    break

        m = _compute_metrics_from_dataset(conn, db_sym)
        conn.close()
        if m:
            symbol_metrics[db_sym].append(m)

    final_metrics = {}
    for sym, m_list in symbol_metrics.items():
        avg_m = {
            dim: (
                sum(x[dim] for x in m_list if x[dim] is not None) / len([x for x in m_list if x[dim] is not None])
                if any(x[dim] is not None for x in m_list)
                else None
            )
            for dim in m_list[0].keys()
        }
        if sum(1 for v in avg_m.values() if v is not None) >= 3:
            final_metrics[sym] = avg_m
            print(f"  ✅ {sym}: processed {len(m_list)} datasets")

    if not final_metrics:
        print("  ❌ No metrics computed.")
        return

    all_m = list(final_metrics.values())
    normalized = [_normalize(m, NORM_MIN, NORM_MAX) for m in all_m]
    centroids, assignments = kmeans(normalized, min(args.k, len(all_m)))

    symbols_list = list(final_metrics.keys())
    cluster_names = _generate_cluster_names(len(centroids))
    clusters = {}
    for c_idx in range(len(centroids)):
        members = [symbols_list[i] for i in range(len(symbols_list)) if assignments[i] == c_idx]
        denorm = {
            dim: centroids[c_idx].get(dim, 0.5) * (NORM_MAX[dim] - NORM_MIN[dim]) + NORM_MIN[dim] for dim in NORM_MIN
        }
        clusters[cluster_names[c_idx]] = {"centroid": denorm, "members": members, "n_members": len(members)}

    config = {
        "version": "3.1",
        "dimensions": list(NORM_MIN.keys()),
        "normalization": {"min": NORM_MIN, "max": NORM_MAX},
        "clusters": clusters,
    }
    with open(args.output, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n  ✅ Saved to {args.output}")


if __name__ == "__main__":
    main()
