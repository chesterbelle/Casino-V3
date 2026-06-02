#!/usr/bin/env python3
"""
Cluster Builder — Offline Clustering Pipeline (Institutional 4 Dimensions)

Computes 4 microstructure dimensions and runs K-Means clustering.

Dimensions (institutional):
  1. tick_size_efficiency: how fast spread clears (trades that narrow / total)
  2. book_density: total volume across L2 levels, normalized by spread
  3. volume_vol_ratio: energy to move price (total USD volume / volatility)
  4. speed: trades per second

Usage:
    # Build clusters from exchange data (live)
    python utils/cluster_builder.py --exchange --k 5

    # Build clusters from DB data
    python utils/cluster_builder.py --db data/historian.db --k 5

    # Find optimal k
    python utils/cluster_builder.py --exchange --optimize-k
"""

import argparse
import asyncio
import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, ".")

CLUSTERS_PATH = Path("config/clusters.json")

# Fixed normalization ranges for 4 institutional dimensions
# Use log1p scaling for book_density and volume_vol_ratio to handle huge range
NORM_MIN = {
    "tick_size_efficiency": 0.0,
    "book_density": 0.0,
    "volume_vol_ratio": 0.0,
    "speed": 0.0,
}
NORM_MAX = {
    "tick_size_efficiency": 1.0,
    "book_density": 20.0,  # Will use log1p scaled values
    "volume_vol_ratio": 12.0,  # Will use log1p scaled values
    "speed": 500.0,
}


def _euclidean_distance(a: dict, b: dict) -> float:
    keys = set(a.keys()) & set(b.keys())
    if not keys:
        return float("inf")
    return math.sqrt(sum((a.get(k, 0) - b.get(k, 0)) ** 2 for k in keys))


def _normalize(metrics: dict, norm_min: dict, norm_max: dict) -> dict:
    normalized = {}
    for key, value in metrics.items():
        if value is None:
            normalized[key] = 0.5
            continue
        # Apply log1p scaling for huge-range dimensions
        if key in ("book_density", "volume_vol_ratio") and value > 0:
            value = math.log1p(value)
        min_val = norm_min.get(key, 0)
        max_val = norm_max.get(key, 1)
        if max_val <= min_val:
            normalized[key] = 0.5
            continue
        normalized[key] = max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
    return normalized


# ──────────────────────────────────────────────────────────────
# Exchange Data Fetching (Adapter-first, fallback to direct)
# ──────────────────────────────────────────────────────────────


async def fetch_exchange_data(symbol: str, adapter=None) -> Tuple[Optional[Dict], List[Dict]]:
    """
    Fetch L2 order book and recent trades for a symbol.

    Uses adapter if available (preferred), falls back to direct API calls for standalone CLI.

    Args:
        symbol: Unified symbol (e.g., "BTC/USDT:USDT")
        adapter: Optional ExchangeAdapter instance

    Returns:
        Tuple of (order_book, trades)
    """
    order_book = None
    trades = []

    if adapter and hasattr(adapter, "fetch_order_book") and hasattr(adapter, "fetch_trades"):
        try:
            order_book = await adapter.fetch_order_book(symbol, limit=20)
            trades = await adapter.fetch_trades(symbol, limit=1000)
            return order_book, trades
        except Exception as e:
            print(f"  ⚠️ Adapter fetch failed for {symbol}: {e}, falling back to direct API")

    # Fallback: direct API calls (for standalone CLI usage)
    order_book = await _fetch_direct_l2(symbol)
    trades = await _fetch_direct_trades(symbol, limit=1000)
    return order_book, trades


async def _fetch_direct_l2(symbol: str) -> Optional[Dict]:
    """Fetch L2 order book directly from Binance Futures (fallback for standalone CLI)."""
    try:
        import aiohttp

        base_url = "https://fapi.binance.com"
        if "/" in symbol:
            binance_symbol = symbol.split("/")[0] + "USDT"
        elif symbol.endswith(":USDT"):
            binance_symbol = symbol.replace(":USDT", "")
        else:
            binance_symbol = symbol
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/fapi/v1/depth", params={"symbol": binance_symbol, "limit": 20}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"bids": data.get("bids", []), "asks": data.get("asks", [])}
    except Exception as e:
        print(f"  ⚠️ L2 fetch error for {symbol}: {e}")
    return None


async def _fetch_direct_trades(symbol: str, limit: int = 1000) -> List[Dict]:
    """Fetch recent trades directly from Binance Futures (fallback for standalone CLI)."""
    try:
        import aiohttp

        base_url = "https://fapi.binance.com"
        if "/" in symbol:
            binance_symbol = symbol.split("/")[0] + "USDT"
        elif symbol.endswith(":USDT"):
            binance_symbol = symbol.replace(":USDT", "")
        else:
            binance_symbol = symbol
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/fapi/v1/trades", params={"symbol": binance_symbol, "limit": min(limit, 1000)}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        return data
                    else:
                        print(f"  ⚠️ API error for {symbol}: {data}")
                        return []
                else:
                    print(f"  ⚠️ HTTP {resp.status} for {symbol}")
                    return []
    except Exception as e:
        print(f"  ⚠️ Trades fetch error for {symbol}: {e}")
        return []


# ──────────────────────────────────────────────────────────────
# Dimension Computation (4 Institutional)
# ──────────────────────────────────────────────────────────────


def _compute_tick_size_efficiency(order_book: Dict, trades: List[Dict]) -> Optional[float]:
    """
    Tick Size Efficiency: ratio of trades that narrow the spread.

    A trade narrows the spread if:
    - BUY at best ask (absorbs liquidity, narrows from top)
    - SELL at best bid (absorbs liquidity, narrows from bottom)

    Range: 0.0 (all trades widen) to 1.0 (all trades narrow)
    """
    if not trades or len(trades) < 10:
        return None

    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])
    if not bids or not asks:
        return None

    best_bid = float(bids[0][0]) if isinstance(bids[0], (list, tuple)) else float(bids[0])
    best_ask = float(asks[0][0]) if isinstance(asks[0], (list, tuple)) else float(asks[0])

    narrowing = 0
    total = 0

    for trade in trades:
        price = float(trade.get("price", 0))
        is_buyer_maker = trade.get("isBuyerMaker", False)

        if price <= 0:
            continue

        total += 1

        # Buyer is maker = SELL order hit the bid → widens spread
        # Seller is maker = BUY order hit the ask → narrows spread
        if not is_buyer_maker and price >= best_ask:
            # Buy at ask = narrows from top
            narrowing += 1
        elif is_buyer_maker and price <= best_bid:
            # Sell at bid = narrows from bottom
            narrowing += 1

    return narrowing / total if total > 0 else None


def _compute_book_density(order_book: Dict) -> Optional[float]:
    """
    Book Density: total volume across all 20 L2 levels, normalized by spread.

    Higher = deeper book relative to spread = more institutional.
    Range: 0 (empty book) to 100000+ (massive depth)
    """
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])
    if not bids or not asks:
        return None

    total_volume = sum(float(level[1]) for level in bids) + sum(float(level[1]) for level in asks)

    # Spread in absolute terms
    best_bid = float(bids[0][0]) if isinstance(bids[0], (list, tuple)) else float(bids[0])
    best_ask = float(asks[0][0]) if isinstance(asks[0], (list, tuple)) else float(asks[0])
    mid = (best_bid + best_ask) / 2
    spread_pct = (best_ask - best_bid) / mid if mid > 0 else 0.001

    # Density = volume / spread (higher = deeper book relative to cost)
    return total_volume / spread_pct if spread_pct > 0 else 0


def _compute_volume_vol_ratio(trades: List[Dict]) -> Optional[float]:
    """
    Volume/Volatility Ratio: energy required to move price.

    Higher = more volume relative to vol = harder to move = institutional.
    Range: 0 (no volume) to 100000+ (massive energy)
    """
    if not trades or len(trades) < 20:
        return None

    prices = [float(t["price"]) for t in trades if float(t.get("price", 0)) > 0]
    volumes = [float(t["qty"]) for t in trades]
    usd_volumes = [p * v for p, v in zip(prices, volumes)]

    if len(prices) < 20:
        return None

    # Compute volatility from log returns
    log_rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
    if not log_rets:
        return None

    mean = sum(log_rets) / len(log_rets)
    var = sum((r - mean) ** 2 for r in log_rets) / len(log_rets)
    vol = math.sqrt(var)

    if vol <= 0:
        return None

    # Scale to 1h equivalent
    timestamps = [int(t["time"]) / 1000 for t in trades if t.get("time")]
    if len(timestamps) >= 2:
        time_span = max(timestamps) - min(timestamps)
        if time_span > 0:
            periods_per_hour = 3600 / time_span
            vol_hourly = vol * math.sqrt(periods_per_hour)
        else:
            vol_hourly = vol
    else:
        vol_hourly = vol

    total_usd = sum(usd_volumes)
    return total_usd / (vol_hourly * 1e6) if vol_hourly > 0 else None


def _compute_speed(trades: List[Dict]) -> Optional[float]:
    """
    Speed: trades per second.

    Higher = more active market = more institutional.
    Range: 0 (no activity) to 500+ (ultra-fast)
    """
    if not trades or len(trades) < 10:
        return None

    timestamps = [int(t["time"]) / 1000 for t in trades if t.get("time")]
    if len(timestamps) < 2:
        return None

    time_span = max(timestamps) - min(timestamps)
    return len(trades) / time_span if time_span > 0 else None


def _compute_all_metrics(order_book: Dict, trades: List[Dict]) -> Dict:
    """Compute all 4 institutional dimensions."""
    return {
        "tick_size_efficiency": _compute_tick_size_efficiency(order_book, trades),
        "book_density": _compute_book_density(order_book),
        "volume_vol_ratio": _compute_volume_vol_ratio(trades),
        "speed": _compute_speed(trades),
    }


# ──────────────────────────────────────────────────────────────
# Clustering
# ──────────────────────────────────────────────────────────────


def kmeans(data: List[Dict], k: int, max_iter: int = 100, seed: int = 42) -> Tuple[List[Dict], List[int]]:
    """K-Means clustering on normalized vectors."""
    import random

    random.seed(seed)

    dims = list(data[0].keys())
    n = len(data)

    # K-Means++ initialization
    centroids = [dict(data[random.randint(0, n - 1)])]
    for _ in range(1, k):
        distances = [min(_euclidean_distance(point, c) for c in centroids) for point in data]
        total = sum(distances)
        if total <= 0:
            centroids.append(dict(data[random.randint(0, n - 1)]))
            continue
        probs = [d / total for d in distances]
        r = random.random()
        cumulative = 0
        for i, p in enumerate(probs):
            cumulative += p
            if r <= cumulative:
                centroids.append(dict(data[i]))
                break
        else:
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
    """Compute simplified silhouette score."""
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
                avg_dist = sum(_euclidean_distance(point, o) for o in others) / len(others)
                b = min(b, avg_dist)

        if b == float("inf"):
            continue

        s = (b - a) / max(a, b) if max(a, b) > 0 else 0
        total += s

    return total / len(data) if data else 0


def find_optimal_k(data: List[Dict], k_range: range) -> Tuple[int, float]:
    """Find optimal k using silhouette score."""
    best_k = 3
    best_score = -1

    for k in k_range:
        if k >= len(data):
            break
        centroids, assignments = kmeans(data, k)
        score = compute_silhouette(data, assignments, centroids)
        print(f"  k={k}: silhouette={score:.3f}")
        if score > best_score:
            best_score = score
            best_k = k

    return best_k, best_score


# ──────────────────────────────────────────────────────────────
# Build Clusters
# ──────────────────────────────────────────────────────────────


async def build_clusters_from_exchange(symbols: List[str], k: int = 5, adapter=None) -> Dict:
    """
    Build cluster configuration from live exchange data.

    Args:
        symbols: List of symbols to cluster
        k: Number of clusters
        adapter: Optional ExchangeAdapter instance (preferred over direct API)
    """
    print(f"\n  Fetching live data for {len(symbols)} symbols...")

    symbol_metrics = {}
    for symbol in symbols:
        ob, trades = await fetch_exchange_data(symbol, adapter=adapter)
        if ob and trades:
            metrics = _compute_all_metrics(ob, trades)
            available = sum(1 for v in metrics.values() if v is not None)
            if available >= 3:
                symbol_metrics[symbol] = metrics
                print(f"    ✅ {symbol}: {available}/4 dims")
            else:
                print(f"    ⚠️ {symbol}: only {available}/4 dims (skipped)")
        else:
            print(f"    ❌ {symbol}: no data")

    if len(symbol_metrics) < 2:
        print(f"\n  ⚠️ Not enough symbols ({len(symbol_metrics)})")
        return {}

    all_metrics = list(symbol_metrics.values())
    dims = list(all_metrics[0].keys())
    normalized = [_normalize(m, NORM_MIN, NORM_MAX) for m in all_metrics]

    actual_k = min(k, len(symbol_metrics))
    print(f"\n  Running K-Means (k={actual_k})...")
    centroids, assignments = kmeans(normalized, actual_k)
    silhouette = compute_silhouette(normalized, assignments, centroids)
    print(f"  Silhouette score: {silhouette:.3f}")

    symbols_list = list(symbol_metrics.keys())
    cluster_names = _generate_cluster_names(actual_k)

    clusters = {}
    for c_idx in range(actual_k):
        members = [symbols_list[i] for i in range(len(symbols_list)) if assignments[i] == c_idx]
        denorm_centroid = {}
        for dim in dims:
            min_v = NORM_MIN.get(dim, 0)
            max_v = NORM_MAX.get(dim, 1)
            denorm_centroid[dim] = centroids[c_idx].get(dim, 0.5) * (max_v - min_v) + min_v

        clusters[cluster_names[c_idx]] = {
            "centroid": denorm_centroid,
            "members": members,
            "n_members": len(members),
        }

    config = {
        "version": "3.0",
        "description": "Institutional 4-dimension microstructure clusters.",
        "dimensions": dims,
        "normalization": {"min": NORM_MIN, "max": NORM_MAX},
        "clusters": clusters,
        "threshold": {"max_distance": 0.35},
        "metadata": {
            "created": __import__("datetime").datetime.now().isoformat(),
            "algorithm": "kmeans",
            "k": actual_k,
            "silhouette_score": silhouette,
        },
    }

    return config


def _generate_cluster_names(k: int) -> List[str]:
    default_names = [
        "MEGA_LIQUID",
        "MAJOR_LIQUID",
        "MID_LIQUID",
        "THIN_VOLATILE",
        "ILLIQUID_SPEC",
        "CLUSTER_6",
        "CLUSTER_7",
        "CLUSTER_8",
    ]
    return default_names[:k]


# ──────────────────────────────────────────────────────────────
# DB Mode
# ──────────────────────────────────────────────────────────────


def compute_metrics_from_db(conn: sqlite3.Connection, symbol: str) -> Optional[Dict]:
    """Compute 4 institutional dimensions from DB data."""
    try:
        tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        # book_density from depth_snapshots
        book_density = None
        tick_size_efficiency = 0.5
        if "depth_snapshots" in tables:
            row = conn.execute(
                "SELECT bids, asks FROM depth_snapshots WHERE symbol=? ORDER BY timestamp DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row:
                bids = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                asks = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                if bids and asks:
                    bp = float(bids[0][0]) if isinstance(bids[0], (list, tuple)) else float(bids[0])
                    ap = float(asks[0][0]) if isinstance(asks[0], (list, tuple)) else float(asks[0])
                    mid = (bp + ap) / 2
                    spread_pct = (ap - bp) / mid if mid > 0 else 0.001
                    total_vol = sum(
                        float(level[1]) if isinstance(level, (list, tuple)) else 0.0 for level in bids
                    ) + sum(float(level[1]) if isinstance(level, (list, tuple)) else 0.0 for level in asks)
                    book_density = total_vol / spread_pct if spread_pct > 0 else 0.0

        # speed from price_samples or price_candles
        speed = None
        target_table = "price_samples" if "price_samples" in tables else "price_candles"
        price_col = "price" if "price_samples" in tables else "close"

        if target_table in tables:
            row = conn.execute(
                f"SELECT COUNT(*), MAX(timestamp)-MIN(timestamp) FROM {target_table} WHERE symbol=?",
                (symbol,),
            ).fetchone()
            if row and row[1] and float(row[1]) > 0:
                speed = float(row[0]) / float(row[1])

        # volume_vol_ratio from price_samples or price_candles
        volume_vol_ratio = None
        if target_table in tables:
            rows = conn.execute(
                f"SELECT {price_col} FROM {target_table} WHERE symbol=? ORDER BY timestamp DESC LIMIT 14400",
                (symbol,),
            ).fetchall()
            prices = [float(r[0]) for r in rows if r[0] and float(r[0]) > 0]
            if len(prices) >= 50:
                log_rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
                if log_rets:
                    mean = sum(log_rets) / len(log_rets)
                    var = sum((r - mean) ** 2 for r in log_rets) / len(log_rets)
                    vol = math.sqrt(var)
                    if vol > 0:
                        row = conn.execute(
                            f"SELECT SUM(ABS({price_col}*volume)) FROM {target_table} WHERE symbol=? AND volume>0",
                            (symbol,),
                        ).fetchone()
                        if row and row[0]:
                            volume_vol_ratio = float(row[0]) / (vol * 1e6)
                        else:
                            # Fallback estimation if volume column missing/empty
                            n = len(log_rets)
                            avg_abs_ret = sum(abs(r) for r in log_rets) / n if n > 0 else 0
                            volume_vol_ratio = avg_abs_ret * 1e6 / (vol + 1e-9)

        metrics = {
            "tick_size_efficiency": tick_size_efficiency,
            "book_density": book_density,
            "volume_vol_ratio": volume_vol_ratio,
            "speed": speed,
        }

        return metrics

    except Exception as e:
        print(f"  ⚠️ Error computing metrics for {symbol}: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Cluster Builder — Institutional 4-dimension clustering")
    parser.add_argument("--db", default="data/historian.db", help="Database path")
    parser.add_argument("--k", type=int, default=5, help="Number of clusters")
    parser.add_argument("--optimize-k", action="store_true", help="Find optimal k using silhouette")
    parser.add_argument("--exchange", action="store_true", help="Build clusters from live exchange data")
    parser.add_argument(
        "--symbols",
        type=str,
        default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,LTCUSDT,AVAXUSDT,DOGEUSDT,ADAUSDT,LINKUSDT,NEARUSDT,SUIUSDT,APTUSDT,OPUSDT,ARBUSDT",
        help="Comma-separated symbols for exchange mode",
    )
    parser.add_argument("--output", default="config/clusters.json", help="Output file")
    args = parser.parse_args()

    if args.exchange:
        print(f"\n{'═' * 65}")
        print(f"  BUILDING CLUSTERS FROM EXCHANGE (k={args.k})")
        print(f"{'═' * 65}")
        symbols = [s.strip() for s in args.symbols.split(",")]
        config = asyncio.run(build_clusters_from_exchange(symbols, args.k))
        if config:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(config, f, indent=2)
            print(f"\n  ✅ Saved to {output_path}")
            for name, cluster in config["clusters"].items():
                print(f"    {name}: {cluster['n_members']} members — {cluster['members']}")
        return

    if args.optimize_k:
        print(f"\n{'═' * 65}")
        print(f"  OPTIMIZING K")
        print(f"{'═' * 65}")
        conn = sqlite3.connect(args.db)
        symbols = [row[0] for row in conn.execute("SELECT DISTINCT symbol FROM signals").fetchall()]
        all_metrics = []
        for symbol in symbols:
            metrics = compute_metrics_from_db(conn, symbol)
            if metrics:
                available = sum(1 for v in metrics.values() if v is not None)
                if available >= 3:
                    all_metrics.append(metrics)
        conn.close()

        if len(all_metrics) < 3:
            print(f"  ⚠️ Not enough data ({len(all_metrics)} symbols)")
            return

        normalized = [_normalize(m, NORM_MIN, NORM_MAX) for m in all_metrics]
        best_k, best_score = find_optimal_k(normalized, range(2, min(9, len(all_metrics))))
        print(f"\n  Optimal k: {best_k} (silhouette: {best_score:.3f})")
        return

    # DB mode
    print(f"\n{'═' * 65}")
    print(f"  BUILDING CLUSTERS FROM DB (k={args.k})")
    print(f"{'═' * 65}")
    conn = sqlite3.connect(args.db)
    config = build_clusters_from_db(conn, args.k)
    conn.close()

    if config:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\n  ✅ Saved to {output_path}")
        for name, cluster in config["clusters"].items():
            print(f"    {name}: {cluster['n_members']} members — {cluster['members']}")


def build_clusters_from_db(conn: sqlite3.Connection, k: int) -> Dict:
    """Build clusters from DB data."""
    symbols = [row[0] for row in conn.execute("SELECT DISTINCT symbol FROM signals").fetchall()]
    print(f"  Computing metrics for {len(symbols)} symbols...")

    symbol_metrics = {}
    for symbol in symbols:
        metrics = compute_metrics_from_db(conn, symbol)
        if metrics:
            available = sum(1 for v in metrics.values() if v is not None)
            if available >= 3:
                symbol_metrics[symbol] = metrics
                print(f"    ✅ {symbol}: {available}/4 dims")
            else:
                print(f"    ⚠️ {symbol}: only {available}/4 dims (skipped)")

    if len(symbol_metrics) < 2:
        print(f"  ⚠️ Not enough symbols ({len(symbol_metrics)})")
        return {}

    all_metrics = list(symbol_metrics.values())
    dims = list(all_metrics[0].keys())
    normalized = [_normalize(m, NORM_MIN, NORM_MAX) for m in all_metrics]

    actual_k = min(k, len(symbol_metrics))
    print(f"\n  Running K-Means (k={actual_k})...")
    centroids, assignments = kmeans(normalized, actual_k)
    silhouette = compute_silhouette(normalized, assignments, centroids)
    print(f"  Silhouette score: {silhouette:.3f}")

    symbols_list = list(symbol_metrics.keys())
    cluster_names = _generate_cluster_names(actual_k)

    clusters = {}
    for c_idx in range(actual_k):
        members = [symbols_list[i] for i in range(len(symbols_list)) if assignments[i] == c_idx]
        denorm_centroid = {}
        for dim in dims:
            min_v = NORM_MIN.get(dim, 0)
            max_v = NORM_MAX.get(dim, 1)
            denorm_centroid[dim] = centroids[c_idx].get(dim, 0.5) * (max_v - min_v) + min_v

        clusters[cluster_names[c_idx]] = {
            "centroid": denorm_centroid,
            "members": members,
            "n_members": len(members),
        }

    config = {
        "version": "3.0",
        "description": "Institutional 4-dimension microstructure clusters.",
        "dimensions": dims,
        "normalization": {"min": NORM_MIN, "max": NORM_MAX},
        "clusters": clusters,
        "threshold": {"max_distance": 0.35},
        "metadata": {
            "created": __import__("datetime").datetime.now().isoformat(),
            "algorithm": "kmeans",
            "k": actual_k,
            "silhouette_score": silhouette,
        },
    }

    return config


if __name__ == "__main__":
    main()
