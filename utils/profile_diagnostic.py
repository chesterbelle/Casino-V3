#!/usr/bin/env python3
"""
Profile Diagnostic — Validate Coin Profile Assignments (Institutional 4-Dim)

Computes 4 institutional microstructure dimensions and computes distances
to cluster centroids. Identifies:
- Coins that correctly match their cluster
- Coins closest to a different cluster
- Coins that don't match any cluster

Dimensions (institutional):
  1. tick_size_efficiency: how fast spread clears (0-1)
  2. book_density: total volume / spread
  3. volume_vol_ratio: energy to move price
  4. speed: trades per second

Usage:
    python utils/profile_diagnostic.py --symbol LTCUSDT --exchange
    python utils/profile_diagnostic.py --db data/historian.db --all
"""

import argparse
import asyncio
import json
import math
import sqlite3
import sys
from typing import Dict, List, Optional

sys.path.insert(0, ".")

from core.coin_profiler import CoinProfiler


def format_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT"):
        base = symbol[:-4]
        return f"{base}/USDT:USDT"
    return symbol


# ──────────────────────────────────────────────────────────────
# Exchange Data
# ──────────────────────────────────────────────────────────────


async def fetch_exchange_l2(symbol: str) -> Optional[Dict]:
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
        print(f"  ⚠️ L2 fetch error: {e}")
    return None


async def fetch_exchange_trades(symbol: str, limit: int = 1000) -> List[Dict]:
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
                    return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  ⚠️ Trades fetch error: {e}")
    return []


# ──────────────────────────────────────────────────────────────
# Dimension Computation (4 Institutional)
# ──────────────────────────────────────────────────────────────


def compute_tick_size_efficiency(order_book: Dict, trades: List[Dict]) -> Optional[float]:
    if not trades or len(trades) < 10:
        return None
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])
    if not bids or not asks:
        return None
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    narrowing = 0
    total = 0
    for trade in trades:
        price = float(trade.get("price", 0))
        is_buyer_maker = trade.get("isBuyerMaker", False)
        if price <= 0:
            continue
        total += 1
        if not is_buyer_maker and price >= best_ask:
            narrowing += 1
        elif is_buyer_maker and price <= best_bid:
            narrowing += 1
    return narrowing / total if total > 0 else None


def compute_book_density(order_book: Dict) -> Optional[float]:
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])
    if not bids or not asks:
        return None
    total_volume = sum(float(level[1]) for level in bids) + sum(float(level[1]) for level in asks)
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid = (best_bid + best_ask) / 2
    spread_pct = (best_ask - best_bid) / mid if mid > 0 else 0.001
    return total_volume / spread_pct if spread_pct > 0 else 0


def compute_volume_vol_ratio(trades: List[Dict]) -> Optional[float]:
    if not trades or len(trades) < 20:
        return None
    prices = [float(t["price"]) for t in trades if float(t.get("price", 0)) > 0]
    volumes = [float(t["qty"]) for t in trades]
    usd_volumes = [p * v for p, v in zip(prices, volumes)]
    if len(prices) < 20:
        return None
    log_rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
    if not log_rets:
        return None
    mean = sum(log_rets) / len(log_rets)
    var = sum((r - mean) ** 2 for r in log_rets) / len(log_rets)
    vol = math.sqrt(var)
    if vol <= 0:
        return None
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


def compute_speed(trades: List[Dict]) -> Optional[float]:
    if not trades or len(trades) < 10:
        return None
    timestamps = [int(t["time"]) / 1000 for t in trades if t.get("time")]
    if len(timestamps) < 2:
        return None
    time_span = max(timestamps) - min(timestamps)
    return len(trades) / time_span if time_span > 0 else None


def compute_all_metrics_exchange(order_book: Dict, trades: List[Dict]) -> Dict:
    return {
        "tick_size_efficiency": compute_tick_size_efficiency(order_book, trades),
        "book_density": compute_book_density(order_book),
        "volume_vol_ratio": compute_volume_vol_ratio(trades),
        "speed": compute_speed(trades),
    }


# ──────────────────────────────────────────────────────────────
# DB Metrics
# ──────────────────────────────────────────────────────────────


def compute_all_metrics_db(conn: sqlite3.Connection, symbol: str) -> Dict:
    metrics = {}
    tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    # book_density
    metrics["book_density"] = None
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
                total_vol = sum(level[1] if isinstance(level, (list, tuple)) else 0 for level in bids)
                total_vol += sum(level[1] if isinstance(level, (list, tuple)) else 0 for level in asks)
                metrics["book_density"] = total_vol / spread_pct if spread_pct > 0 else 0

    # speed
    metrics["speed"] = None
    if "price_samples" in tables:
        row = conn.execute(
            "SELECT COUNT(*), MAX(timestamp)-MIN(timestamp) FROM price_samples WHERE symbol=?",
            (symbol,),
        ).fetchone()
        if row and row[1] and row[1] > 0:
            metrics["speed"] = row[0] / row[1]

    # volume_vol_ratio
    metrics["volume_vol_ratio"] = None
    if "price_samples" in tables:
        rows = conn.execute(
            "SELECT price FROM price_samples WHERE symbol=? ORDER BY timestamp DESC LIMIT 14400",
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
                        "SELECT SUM(ABS(price*volume)) FROM price_samples WHERE symbol=? AND volume>0",
                        (symbol,),
                    ).fetchone()
                    if row and row[0]:
                        metrics["volume_vol_ratio"] = float(row[0]) / (vol * 1e6)

    # tick_size_efficiency: can't compute from DB alone
    metrics["tick_size_efficiency"] = None

    return metrics


# ──────────────────────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────────────────────


def print_metrics(metrics: Dict):
    labels = {
        "tick_size_efficiency": ("Tick Size Efficiency", "{:.3f}"),
        "book_density": ("Book Density", "{:.0f}"),
        "volume_vol_ratio": ("Volume/Vol Ratio", "{:.0f}"),
        "speed": ("Speed (trades/s)", "{:.2f}"),
    }
    for dim, (label, fmt) in labels.items():
        val = metrics.get(dim)
        if val is not None:
            print(f"    {label:<22} {fmt.format(val)}")
        else:
            print(f"    {label:<22} ⚠️ No data")


def print_distance_table(distances: Dict[str, float], threshold: float):
    print(f"\n  Distance to Cluster Centroids:")
    print(f"  {'─' * 50}")
    for name, dist in distances.items():
        bar_len = min(int(dist * 50), 40)
        bar = "█" * bar_len
        marker = " ✅" if dist <= threshold else ""
        print(f"    {name:<20} {dist:.3f}  {bar}{marker}")
    print(f"\n  Threshold: {threshold:.3f}")


# ──────────────────────────────────────────────────────────────
# Diagnosis
# ──────────────────────────────────────────────────────────────


async def diagnose_symbol_exchange(symbol: str) -> Dict:
    profiler = CoinProfiler()

    print(f"\n{'═' * 65}")
    print(f"  PROFILE DIAGNOSTIC — {symbol} (Exchange, 4 Institutional Dims)")
    print(f"{'═' * 65}")

    print(f"\n  Fetching L2 + trades from exchange...")
    ob = await fetch_exchange_l2(symbol)
    trades = await fetch_exchange_trades(symbol, limit=1000)

    if not ob or not trades:
        print(f"  ⚠️ Could not fetch data from exchange")
        return {"symbol": symbol, "verdict": "EXCHANGE_ERROR"}

    metrics = compute_all_metrics_exchange(ob, trades)

    print(f"\n  Real Microstructure Metrics (4 institutional dimensions):")
    print(f"  {'─' * 50}")
    print_metrics(metrics)

    available = sum(1 for v in metrics.values() if v is not None)
    if available < 3:
        print(f"\n  ⚠️ Insufficient metrics (need ≥3, have {available})")
        return {"symbol": symbol, "verdict": "INSUFFICIENT_DATA", "metrics": metrics}

    distances = profiler.get_distances(metrics)
    threshold = profiler.threshold

    print_distance_table(distances, threshold)

    if distances:
        closest = min(distances, key=distances.get)
        min_dist = distances[closest]
        if min_dist <= threshold:
            print(f"\n  VERDICT: ✅ MATCH → {closest} (distance: {min_dist:.3f})")
            return {
                "symbol": symbol,
                "verdict": "MATCH",
                "profile": closest,
                "distance": min_dist,
                "metrics": metrics,
                "distances": distances,
            }
        else:
            print(f"\n  VERDICT: ⚠️ NO MATCH — closest is {closest} (distance: {min_dist:.3f} > {threshold})")
            return {
                "symbol": symbol,
                "verdict": "NO_MATCH",
                "closest_profile": closest,
                "distance": min_dist,
                "metrics": metrics,
                "distances": distances,
            }

    return {"symbol": symbol, "verdict": "ERROR", "metrics": metrics}


def diagnose_symbol_db(conn: sqlite3.Connection, symbol: str) -> Dict:
    profiler = CoinProfiler()

    print(f"\n{'═' * 65}")
    print(f"  PROFILE DIAGNOSTIC — {symbol}")
    print(f"{'═' * 65}")

    signal_count = conn.execute("SELECT COUNT(*) FROM signals WHERE symbol = ?", (symbol,)).fetchone()[0]
    print(f"\n  Signals in DB: {signal_count}")

    if signal_count < 5:
        print(f"  ⚠️ Insufficient signals (need ≥5, have {signal_count})")
        return {"symbol": symbol, "verdict": "INSUFFICIENT_DATA"}

    print(f"\n  Computing 4 institutional metrics...")
    metrics = compute_all_metrics_db(conn, symbol)

    print(f"\n  Real Microstructure Metrics:")
    print(f"  {'─' * 50}")
    print_metrics(metrics)

    available = sum(1 for v in metrics.values() if v is not None)
    if available < 3:
        print(f"\n  ⚠️ Insufficient metrics (need ≥3, have {available})")
        return {"symbol": symbol, "verdict": "INSUFFICIENT_DATA", "metrics": metrics}

    distances = profiler.get_distances(metrics)
    threshold = profiler.threshold

    print_distance_table(distances, threshold)

    if distances:
        closest = min(distances, key=distances.get)
        min_dist = distances[closest]
        if min_dist <= threshold:
            print(f"\n  VERDICT: ✅ MATCH → {closest} (distance: {min_dist:.3f})")
            return {
                "symbol": symbol,
                "verdict": "MATCH",
                "profile": closest,
                "distance": min_dist,
                "metrics": metrics,
                "distances": distances,
            }
        else:
            print(f"\n  VERDICT: ⚠️ NO MATCH — closest is {closest} (distance: {min_dist:.3f} > {threshold})")
            return {
                "symbol": symbol,
                "verdict": "NO_MATCH",
                "closest_profile": closest,
                "distance": min_dist,
                "metrics": metrics,
                "distances": distances,
            }

    return {"symbol": symbol, "verdict": "ERROR", "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description="Profile Diagnostic — 4 institutional dimensions")
    parser.add_argument("--db", default="data/historian.db", help="Database path")
    parser.add_argument("--symbol", help="Specific symbol to diagnose")
    parser.add_argument("--all", action="store_true", help="Diagnose all coins in DB")
    parser.add_argument("--exchange", action="store_true", help="Use exchange data (real-time)")
    args = parser.parse_args()

    if not args.symbol and not args.all:
        parser.error("Must specify --symbol or --all")

    conn = None
    try:
        conn = sqlite3.connect(args.db)
    except Exception:
        pass

    if args.exchange and args.symbol:
        result = asyncio.run(diagnose_symbol_exchange(args.symbol))
    elif args.symbol:
        result = diagnose_symbol_db(conn, args.symbol)
    else:
        coins = conn.execute("SELECT DISTINCT symbol FROM signals").fetchall()
        symbols = [c[0] for c in coins]

        print(f"\n{'═' * 65}")
        print(f"  PROFILE DIAGNOSTIC — ALL COINS (4 institutional dims)")
        print(f"{'═' * 65}")
        print(f"\n  Analyzing {len(symbols)} coins...")

        results = []
        for symbol in sorted(symbols):
            result = diagnose_symbol_db(conn, symbol)
            results.append(result)

        print(f"\n\n{'═' * 65}")
        print(f"  SUMMARY")
        print(f"{'═' * 65}")

        matches = [r for r in results if r["verdict"] == "MATCH"]
        no_match = [r for r in results if r["verdict"] == "NO_MATCH"]
        insufficient = [r for r in results if r["verdict"] == "INSUFFICIENT_DATA"]

        print(f"\n  ✅ MATCH:      {len(matches)}/{len(results)}")
        print(f"  ⚠️ NO MATCH:   {len(no_match)}/{len(results)}")
        print(f"  ⚠️ NO DATA:    {len(insufficient)}/{len(results)}")

        if no_match:
            print(f"\n  Coins not matching any cluster:")
            for r in no_match:
                print(
                    f"    - {r['symbol']} → closest: {r.get('closest_profile', '?')} (dist: {r.get('distance', '?'):.3f})"
                )

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
