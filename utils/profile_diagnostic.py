#!/usr/bin/env python3
"""
Profile Diagnostic — Validate Coin Profile Assignments

Analyzes real microstructure metrics and compares against current
profile characteristics. Identifies:
- Coins that correctly match their profile
- Coins that should be reassigned to a different profile
- Coins that don't match any profile (need new profile creation)

Data sources (in order of preference):
1. Exchange L2 data (real-time, most accurate)
2. historian.db depth_snapshots (if available)
3. historian.db price_samples (speed only)

Usage:
    # Diagnose a specific coin (uses exchange data)
    python utils/profile_diagnostic.py --symbol LTCUSDT

    # Diagnose all coins in DB
    python utils/profile_diagnostic.py --db data/historian.db --all

    # Diagnose with exchange data only (no DB required)
    python utils/profile_diagnostic.py --symbol LTCUSDT --exchange
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, ".")

from config.coin_profiles import COIN_PROFILES, DEFAULT_PROFILE


def format_symbol(symbol: str) -> str:
    """Convert symbol to CCXT format (e.g., LTCUSDT -> LTC/USDT:USDT)."""
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT"):
        base = symbol[:-4]
        return f"{base}/USDT:USDT"
    return symbol


async def fetch_exchange_l2(symbol: str) -> Optional[Dict]:
    """Fetch L2 depth data from exchange using REST API."""
    try:
        import aiohttp

        # Binance Futures testnet REST API
        base_url = "https://testnet.binancefuture.com"
        endpoint = "/fapi/v1/depth"

        # Convert symbol to Binance format (LTCUSDT)
        if "/" in symbol:
            binance_symbol = symbol.split("/")[0] + "USDT"
        elif symbol.endswith(":USDT"):
            binance_symbol = symbol.replace(":USDT", "")
        else:
            binance_symbol = symbol

        url = f"{base_url}{endpoint}"
        params = {"symbol": binance_symbol, "limit": 20}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "symbol": binance_symbol,
                        "bids": data.get("bids", []),
                        "asks": data.get("asks", []),
                        "timestamp": data.get("lastUpdateId", 0),
                    }
                else:
                    print(f"  ⚠️ API returned status {response.status}")
                    return None

    except Exception as e:
        print(f"  ⚠️ Error fetching exchange L2 data: {e}")
        return None


def compute_spread_ratio_from_exchange(order_book: Dict) -> Optional[float]:
    """Compute spread_ratio from exchange order book."""
    try:
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        if not bids or not asks or len(bids) == 0 or len(asks) == 0:
            return None

        # Current spread
        bid_price = float(bids[0][0])
        ask_price = float(asks[0][0])
        current_spread = ask_price - bid_price

        # For spread_ratio, we need historical data to compare
        # With single snapshot, we can only report the absolute spread
        # Return 1.0 as neutral (can't compute ratio without history)
        # But we can compute spread as percentage of mid price
        mid_price = (bid_price + ask_price) / 2
        spread_pct = current_spread / mid_price * 100

        # Map spread percentage to a ratio-like metric
        # Typical spreads: BTC ~0.01%, ALT ~0.03-0.1%
        # Spread ratio > 1.0 means wider than normal
        if spread_pct < 0.02:
            return 0.8  # Very tight (BTC-like)
        elif spread_pct < 0.05:
            return 1.0  # Normal
        elif spread_pct < 0.10:
            return 1.3  # Wide
        else:
            return 1.8  # Very wide

    except Exception as e:
        print(f"  ⚠️ Error computing spread_ratio: {e}")
        return None


def compute_depth_ratio_from_exchange(order_book: Dict) -> Optional[float]:
    """Compute depth_ratio from exchange order book: bid_vol / ask_vol within 0.2% of mid."""
    try:
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        if not bids or not asks or len(bids) == 0 or len(asks) == 0:
            return None

        # Calculate mid price
        bid_price = float(bids[0][0])
        ask_price = float(asks[0][0])
        mid_price = (bid_price + ask_price) / 2

        # Sum volume within 0.2% of mid
        tolerance = mid_price * 0.002

        bid_vol = sum(float(level[1]) for level in bids if abs(float(level[0]) - mid_price) <= tolerance)

        ask_vol = sum(float(level[1]) for level in asks if abs(float(level[0]) - mid_price) <= tolerance)

        if ask_vol <= 0:
            return None

        return bid_vol / ask_vol

    except Exception as e:
        print(f"  ⚠️ Error computing depth_ratio: {e}")
        return None


def compute_spread_ratio(conn: sqlite3.Connection, symbol: str) -> Optional[float]:
    """Compute spread_ratio from depth_snapshots: current_spread / avg_5m_spread."""
    try:
        # Check if table exists
        tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "depth_snapshots" not in tables:
            return None

        # Get recent depth snapshots
        rows = conn.execute(
            """
            SELECT timestamp, bids, asks
            FROM depth_snapshots
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 300
            """,
            (symbol,),
        ).fetchall()

        if len(rows) < 10:
            return None

        spreads = []
        for ts, bids_json, asks_json in rows:
            try:
                bids = json.loads(bids_json) if isinstance(bids_json, str) else bids_json
                asks = json.loads(asks_json) if isinstance(asks_json, str) else asks_json
                if bids and asks and len(bids) > 0 and len(asks) > 0:
                    bid_price = bids[0][0] if isinstance(bids[0], (list, tuple)) else bids[0]
                    ask_price = asks[0][0] if isinstance(asks[0], (list, tuple)) else asks[0]
                    spread = ask_price - bid_price
                    spreads.append((ts, spread))
            except (json.JSONDecodeError, IndexError, TypeError):
                continue

        if len(spreads) < 10:
            return None

        # Current spread (most recent)
        current_spread = spreads[0][1]

        # Average spread over 5 minutes (300 seconds)
        recent_spreads = [s[1] for s in spreads[:300]]
        avg_5m_spread = sum(recent_spreads) / len(recent_spreads) if recent_spreads else 1

        if avg_5m_spread <= 0:
            return None

        return current_spread / avg_5m_spread

    except Exception as e:
        print(f"  ⚠️ Error computing spread_ratio for {symbol}: {e}")
        return None


def compute_depth_ratio(conn: sqlite3.Connection, symbol: str) -> Optional[float]:
    """Compute depth_ratio from depth_snapshots: bid_vol / ask_vol within 0.2% of mid."""
    try:
        # Check if table exists
        tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "depth_snapshots" not in tables:
            return None

        # Get most recent depth snapshot
        row = conn.execute(
            """
            SELECT bids, asks
            FROM depth_snapshots
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (symbol,),
        ).fetchone()

        if not row:
            return None

        bids_json, asks_json = row
        bids = json.loads(bids_json) if isinstance(bids_json, str) else bids_json
        asks = json.loads(asks_json) if isinstance(asks_json, str) else asks_json

        if not bids or not asks or len(bids) == 0 or len(asks) == 0:
            return None

        # Calculate mid price
        bid_price = bids[0][0] if isinstance(bids[0], (list, tuple)) else bids[0]
        ask_price = asks[0][0] if isinstance(asks[0], (list, tuple)) else asks[0]
        mid_price = (bid_price + ask_price) / 2

        # Sum volume within 0.2% of mid
        tolerance = mid_price * 0.002
        bid_vol = sum(
            level[1] if isinstance(level, (list, tuple)) else level
            for level in bids
            if abs((level[0] if isinstance(level, (list, tuple)) else level) - mid_price) <= tolerance
        )
        ask_vol = sum(
            level[1] if isinstance(level, (list, tuple)) else level
            for level in asks
            if abs((level[0] if isinstance(level, (list, tuple)) else level) - mid_price) <= tolerance
        )

        if ask_vol <= 0:
            return None

        return bid_vol / ask_vol

    except Exception as e:
        print(f"  ⚠️ Error computing depth_ratio for {symbol}: {e}")
        return None


def compute_speed(conn: sqlite3.Connection, symbol: str) -> Optional[float]:
    """Compute speed (trades per second) from price_samples."""
    try:
        # Check if table exists
        tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "price_samples" not in tables:
            return None

        row = conn.execute(
            """
            SELECT COUNT(*) as sample_count,
                   MAX(timestamp) - MIN(timestamp) as time_span
            FROM price_samples
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()

        if not row or row[1] is None or row[1] <= 0:
            return None

        sample_count, time_span = row
        return sample_count / time_span

    except Exception as e:
        print(f"  ⚠️ Error computing speed for {symbol}: {e}")
        return None


def match_profile(metrics: Dict) -> Optional[str]:
    """Try to match coin metrics against profiles. Returns profile name or None."""
    for profile_name, profile_config in COIN_PROFILES.items():
        if profile_name == DEFAULT_PROFILE:
            continue

        characteristics = profile_config.get("characteristics", {})
        match = True

        for feature, ranges in characteristics.items():
            actual = metrics.get(feature)
            if actual is None:
                match = False
                break

            min_val = ranges.get("min", 0)
            max_val = ranges.get("max", float("inf"))

            if not (min_val <= actual <= max_val):
                match = False
                break

        if match:
            return profile_name

    return None


def find_closest_profile(metrics: Dict) -> Tuple[str, List[str]]:
    """Find the closest profile and which features don't match."""
    best_profile = None
    best_score = -1
    mismatches = []

    for profile_name, profile_config in COIN_PROFILES.items():
        if profile_name == DEFAULT_PROFILE:
            continue

        characteristics = profile_config.get("characteristics", {})
        score = 0
        profile_mismatches = []

        for feature, ranges in characteristics.items():
            actual = metrics.get(feature)
            if actual is None:
                profile_mismatches.append(f"{feature} (no data)")
                continue

            min_val = ranges.get("min", 0)
            max_val = ranges.get("max", float("inf"))

            if min_val <= actual <= max_val:
                score += 1
            else:
                if actual < min_val:
                    profile_mismatches.append(f"{feature} ({actual:.3f} < {min_val})")
                else:
                    profile_mismatches.append(f"{feature} ({actual:.3f} > {max_val})")

        if score > best_score:
            best_score = score
            best_profile = profile_name
            mismatches = profile_mismatches

    return best_profile, mismatches


def suggest_new_profile(metrics: Dict, symbol: str) -> Dict:
    """Suggest parameters for a new profile based on metrics."""
    spread = metrics.get("spread_ratio", 1.0)
    depth = metrics.get("depth_ratio", 1.0)
    speed = metrics.get("speed", 0.05)

    # Suggest characteristics with some margin
    suggested = {
        "name": f"CUSTOM_{symbol.split('/')[0] if '/' in symbol else symbol}",
        "characteristics": {
            "spread_ratio": {"min": 0.0, "max": round(spread * 1.3, 2)},
            "depth_ratio": {"min": 0.0, "max": round(depth * 1.3, 2)},
            "speed": {"min": 0.0, "max": round(speed * 1.3, 4)},
        },
        "parameters": {
            "z_score_min": 2.5,
            "concentration_min": 0.45,
            "noise_max": 0.35,
            "tp_pct": 0.009,
            "sl_pct": 0.009,
            "l2_ratio_min": 1.5,
        },
    }

    # Adjust parameters based on depth
    if depth < 1.0:
        suggested["parameters"]["z_score_min"] = 2.0
        suggested["parameters"]["concentration_min"] = 0.35
        suggested["parameters"]["l2_ratio_min"] = 1.0
    elif depth > 3.0:
        suggested["parameters"]["z_score_min"] = 3.5
        suggested["parameters"]["concentration_min"] = 0.60
        suggested["parameters"]["l2_ratio_min"] = 2.5

    return suggested


async def diagnose_symbol_exchange(symbol: str) -> Dict:
    """Run diagnosis using exchange L2 data."""
    print(f"\n{'═' * 65}")
    print(f"  PROFILE DIAGNOSTIC — {symbol} (Exchange Data)")
    print(f"{'═' * 65}")

    print(f"\n  Fetching L2 data from exchange...")

    # Fetch order book from exchange
    order_book = await fetch_exchange_l2(symbol)

    if not order_book:
        print(f"  ⚠️ Could not fetch L2 data from exchange")
        return {"symbol": symbol, "verdict": "EXCHANGE_ERROR"}

    # Compute metrics from exchange data
    spread_ratio = compute_spread_ratio_from_exchange(order_book)
    depth_ratio = compute_depth_ratio_from_exchange(order_book)

    # Get speed from DB if available
    speed = None
    try:
        conn = sqlite3.connect("data/historian.db")
        speed = compute_speed(conn, format_symbol(symbol))
        conn.close()
    except Exception:
        pass

    metrics = {
        "spread_ratio": spread_ratio,
        "depth_ratio": depth_ratio,
        "speed": speed,
    }

    print(f"\n  Real Metrics (Exchange):")
    print(f"    spread_ratio:  {spread_ratio:.3f}" if spread_ratio else "    spread_ratio:  ⚠️ No data")
    print(f"    depth_ratio:   {depth_ratio:.3f}" if depth_ratio else "    depth_ratio:   ⚠️ No data")
    print(f"    speed:         {speed:.4f}" if speed else "    speed:         ⚠️ No data (from DB)")

    # Show raw order book info
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])
    if bids and asks:
        bid_price = float(bids[0][0])
        ask_price = float(asks[0][0])
        spread = ask_price - bid_price
        mid_price = (bid_price + ask_price) / 2
        spread_pct = spread / mid_price * 100

        print(f"\n  Order Book Snapshot:")
        print(f"    Best Bid:      {bid_price:.2f}")
        print(f"    Best Ask:      {ask_price:.2f}")
        print(f"    Spread:        {spread:.4f} ({spread_pct:.4f}%)")
        print(f"    Bid Levels:    {len(bids)}")
        print(f"    Ask Levels:    {len(asks)}")

    # Check if we have enough data
    available_metrics = [v for v in metrics.values() if v is not None]
    if len(available_metrics) < 2:
        print(f"\n  ⚠️ Insufficient metrics data (need ≥2, have {len(available_metrics)})")
        return {"symbol": symbol, "verdict": "INSUFFICIENT_DATA", "metrics": metrics}

    # Match against profiles
    print(f"\n  Profile Comparison:")
    print(f"  {'─' * 60}")

    matched_profile = match_profile(metrics)

    if matched_profile:
        print(f"  ✅ MATCH: {matched_profile}")
        print(f"  {'─' * 60}")
        print(f"\n  VERDICT: ✅ MATCH")
        print(f"  {symbol} correctly matches {matched_profile}")
        return {
            "symbol": symbol,
            "verdict": "MATCH",
            "profile": matched_profile,
            "metrics": metrics,
        }

    # No match - find closest
    closest_profile, mismatches = find_closest_profile(metrics)

    print(f"  ❌ No exact match found")
    print(f"\n  Closest profile: {closest_profile}")
    print(f"  Mismatches:")
    for m in mismatches:
        print(f"    - {m}")

    # Check if reassignment is possible
    print(f"\n  {'─' * 60}")

    # Check all profiles
    for profile_name, profile_config in COIN_PROFILES.items():
        if profile_name == DEFAULT_PROFILE:
            continue

        characteristics = profile_config.get("characteristics", {})
        match = True
        failing_features = []

        for feature, ranges in characteristics.items():
            actual = metrics.get(feature)
            if actual is None:
                match = False
                failing_features.append(f"{feature} (no data)")
                continue

            min_val = ranges.get("min", 0)
            max_val = ranges.get("max", float("inf"))

            if not (min_val <= actual <= max_val):
                match = False
                if actual < min_val:
                    failing_features.append(f"{feature} ({actual:.3f} < {min_val})")
                else:
                    failing_features.append(f"{feature} ({actual:.3f} > {max_val})")

        if match:
            print(f"  ℹ️ Would match {profile_name} if not for:")
            for f in failing_features:
                print(f"      - {f}")

    # Suggest new profile
    suggestion = suggest_new_profile(metrics, symbol)

    print(f"\n  {'═' * 60}")
    print(f"  VERDICT: ⚠️ CREATE NEW PROFILE")
    print(f"  {'═' * 60}")
    print(f"\n  {symbol} does NOT match any existing profile.")
    print(f"\n  Suggested New Profile:")
    print(f"    Name: {suggestion['name']}")
    print(f"    Characteristics:")
    for feature, ranges in suggestion["characteristics"].items():
        print(f"      {feature}: < {ranges['max']}")
    print(f"\n  Suggested Parameters:")
    for param, value in suggestion["parameters"].items():
        print(f"      {param}: {value}")

    return {
        "symbol": symbol,
        "verdict": "CREATE",
        "suggestion": suggestion,
        "metrics": metrics,
    }


def diagnose_symbol(conn: sqlite3.Connection, symbol: str) -> Dict:
    """Run full diagnosis for a single symbol from DB."""
    print(f"\n{'═' * 65}")
    print(f"  PROFILE DIAGNOSTIC — {symbol}")
    print(f"{'═' * 65}")

    # Get signal count
    signal_count = conn.execute("SELECT COUNT(*) FROM signals WHERE symbol = ?", (symbol,)).fetchone()[0]

    print(f"\n  Signals in DB: {signal_count}")

    if signal_count < 5:
        print(f"  ⚠️ Insufficient signals (need ≥5, have {signal_count})")
        return {"symbol": symbol, "verdict": "INSUFFICIENT_DATA"}

    # Compute real metrics
    print(f"\n  Computing real metrics...")

    spread_ratio = compute_spread_ratio(conn, symbol)
    depth_ratio = compute_depth_ratio(conn, symbol)
    speed = compute_speed(conn, symbol)

    metrics = {
        "spread_ratio": spread_ratio,
        "depth_ratio": depth_ratio,
        "speed": speed,
    }

    print(f"\n  Real Metrics:")
    print(f"    spread_ratio:  {spread_ratio:.3f}" if spread_ratio else "    spread_ratio:  ⚠️ No data")
    print(f"    depth_ratio:   {depth_ratio:.3f}" if depth_ratio else "    depth_ratio:   ⚠️ No data")
    print(f"    speed:         {speed:.4f}" if speed else "    speed:         ⚠️ No data")

    # Check if we have enough data
    available_metrics = [v for v in metrics.values() if v is not None]
    if len(available_metrics) < 2:
        print(f"\n  ⚠️ Insufficient metrics data (need ≥2, have {len(available_metrics)})")
        return {"symbol": symbol, "verdict": "INSUFFICIENT_DATA", "metrics": metrics}

    # Match against profiles
    print(f"\n  Profile Comparison:")
    print(f"  {'─' * 60}")

    matched_profile = match_profile(metrics)

    if matched_profile:
        print(f"  ✅ MATCH: {matched_profile}")
        print(f"  {'─' * 60}")
        print(f"\n  VERDICT: ✅ MATCH")
        print(f"  {symbol} correctly matches {matched_profile}")
        return {
            "symbol": symbol,
            "verdict": "MATCH",
            "profile": matched_profile,
            "metrics": metrics,
        }

    # No match - find closest
    closest_profile, mismatches = find_closest_profile(metrics)

    print(f"  ❌ No exact match found")
    print(f"\n  Closest profile: {closest_profile}")
    print(f"  Mismatches:")
    for m in mismatches:
        print(f"    - {m}")

    # Check if reassignment is possible
    print(f"\n  {'─' * 60}")

    # Check all profiles
    for profile_name, profile_config in COIN_PROFILES.items():
        if profile_name == DEFAULT_PROFILE:
            continue

        characteristics = profile_config.get("characteristics", {})
        match = True
        failing_features = []

        for feature, ranges in characteristics.items():
            actual = metrics.get(feature)
            if actual is None:
                match = False
                failing_features.append(f"{feature} (no data)")
                continue

            min_val = ranges.get("min", 0)
            max_val = ranges.get("max", float("inf"))

            if not (min_val <= actual <= max_val):
                match = False
                if actual < min_val:
                    failing_features.append(f"{feature} ({actual:.3f} < {min_val})")
                else:
                    failing_features.append(f"{feature} ({actual:.3f} > {max_val})")

        if match:
            print(f"  ℹ️ Would match {profile_name} if not for:")
            for f in failing_features:
                print(f"      - {f}")

    # Suggest new profile
    suggestion = suggest_new_profile(metrics, symbol)

    print(f"\n  {'═' * 60}")
    print(f"  VERDICT: ⚠️ CREATE NEW PROFILE")
    print(f"  {'═' * 60}")
    print(f"\n  {symbol} does NOT match any existing profile.")
    print(f"\n  Suggested New Profile:")
    print(f"    Name: {suggestion['name']}")
    print(f"    Characteristics:")
    for feature, ranges in suggestion["characteristics"].items():
        print(f"      {feature}: < {ranges['max']}")
    print(f"\n  Suggested Parameters:")
    for param, value in suggestion["parameters"].items():
        print(f"      {param}: {value}")

    return {
        "symbol": symbol,
        "verdict": "CREATE",
        "suggestion": suggestion,
        "metrics": metrics,
    }


def main():
    parser = argparse.ArgumentParser(description="Profile Diagnostic — Validate coin profile assignments")
    parser.add_argument("--db", default="data/historian.db", help="Database path")
    parser.add_argument("--symbol", help="Specific symbol to diagnose (e.g., XRPUSDT)")
    parser.add_argument("--all", action="store_true", help="Diagnose all coins in DB")
    parser.add_argument("--exchange", action="store_true", help="Use exchange L2 data (real-time)")
    args = parser.parse_args()

    if not args.symbol and not args.all:
        parser.error("Must specify --symbol or --all")

    if args.exchange and args.symbol:
        # Use exchange data mode
        result = asyncio.run(diagnose_symbol_exchange(args.symbol))
    else:
        # Use DB mode
        conn = sqlite3.connect(args.db)

        if args.symbol:
            # Single symbol diagnosis
            result = diagnose_symbol(conn, args.symbol)
        else:
            # All coins diagnosis
            coins = conn.execute("SELECT DISTINCT symbol FROM signals").fetchall()
            symbols = [c[0] for c in coins]

            print(f"\n{'═' * 65}")
            print(f"  PROFILE DIAGNOSTIC — ALL COINS")
            print(f"{'═' * 65}")
            print(f"\n  Analyzing {len(symbols)} coins...")

            results = []
            for symbol in sorted(symbols):
                result = diagnose_symbol(conn, symbol)
                results.append(result)

            # Summary
            print(f"\n\n{'═' * 65}")
            print(f"  SUMMARY")
            print(f"{'═' * 65}")

            matches = [r for r in results if r["verdict"] == "MATCH"]
            creates = [r for r in results if r["verdict"] == "CREATE"]
            insufficient = [r for r in results if r["verdict"] == "INSUFFICIENT_DATA"]

            print(f"\n  ✅ MATCH:     {len(matches)}/{len(results)}")
            print(f"  ⚠️ CREATE:    {len(creates)}/{len(results)}")
            print(f"  ⚠️ NO DATA:   {len(insufficient)}/{len(results)}")

            if creates:
                print(f"\n  Coins needing new profiles:")
                for r in creates:
                    print(f"    - {r['symbol']} → {r['suggestion']['name']}")

        conn.close()


if __name__ == "__main__":
    main()
