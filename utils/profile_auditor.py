#!/usr/bin/env python3
"""
Profile Auditor — Coin Microstructure Profiling

Analyzes historical data to determine optimal thresholds for coin tiers.
Calculates correlations between microstructure characteristics and edge.
Generates config/coin_profiles.py automatically.

Usage:
    python utils/profile_auditor.py --db data/historian.db
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np


def analyze_coin_microstructure(conn: sqlite3.Connection, symbol: str) -> Dict:
    """Analyze microstructure characteristics for a single coin."""
    # Get price samples
    samples = conn.execute(
        "SELECT timestamp, price FROM price_samples WHERE symbol=? ORDER BY timestamp",
        (symbol,),
    ).fetchall()

    if len(samples) < 100:
        return {}

    prices = [s[1] for s in samples]
    timestamps = [s[0] for s in samples]

    # Trade density (trades per second)
    time_span = timestamps[-1] - timestamps[0]
    trades_per_sec = len(samples) / max(time_span, 1)

    # ATR (Average True Range) - simplified
    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] * 100 for i in range(1, len(prices))]
    atr_pct = np.std(returns) * np.sqrt(1440) if returns else 0  # Annualized to 1m candles

    # Volume proxy: total price movement * sample count
    total_volume_proxy = len(samples) * np.mean(np.abs(returns)) if returns else 0

    return {
        "symbol": symbol,
        "trades_per_sec": trades_per_sec,
        "atr_pct": atr_pct,
        "volume_24h_usd": total_volume_proxy * 1_000_000,  # Proxy in USD
        "n_samples": len(samples),
    }


def analyze_coin_edge(conn: sqlite3.Connection, symbol: str, window: int = 14400) -> Dict:
    """Analyze edge characteristics for a single coin."""
    # Get signals
    signals = conn.execute(
        "SELECT timestamp, side, price, metadata FROM signals WHERE symbol=? ORDER BY timestamp",
        (symbol,),
    ).fetchall()

    if len(signals) < 5:
        return {"n_signals": len(signals), "has_edge": False}

    # Calculate MFE/MAE for each signal
    mfe_values = []
    mae_values = []
    wins = 0
    losses = 0

    for ts, side, price, meta in signals:
        # Get price samples in window
        samples = conn.execute(
            "SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
            (symbol, ts, ts + window),
        ).fetchall()

        if not samples:
            continue

        prices = [s[0] for s in samples]
        if side == "LONG":
            mfe = max((p - price) / price * 100 for p in prices)
            mae = max((price - p) / price * 100 for p in prices)
        else:
            mfe = max((price - p) / price * 100 for p in prices)
            mae = max((p - price) / price * 100 for p in prices)

        mfe_values.append(mfe)
        mae_values.append(mae)

        # Simple win/loss based on 0.90% target
        if mfe >= 0.90:
            wins += 1
        elif mae >= 0.90:
            losses += 1

    if not mfe_values:
        return {"n_signals": len(signals), "has_edge": False}

    avg_mfe = np.mean(mfe_values)
    avg_mae = np.mean(mae_values)
    mfe_mae_ratio = avg_mfe / max(avg_mae, 0.001)
    wr = wins / max(wins + losses, 1) * 100

    # Net Taker estimation
    gross_exp = (wr / 100) * 0.90 - ((100 - wr) / 100) * 0.90
    net_taker = gross_exp - 0.12

    return {
        "n_signals": len(signals),
        "avg_mfe": avg_mfe,
        "avg_mae": avg_mae,
        "mfe_mae_ratio": mfe_mae_ratio,
        "win_rate": wr,
        "net_taker": net_taker,
        "has_edge": net_taker > 0,
    }


def calculate_correlations(coin_data: List[Dict]) -> Dict:
    """Calculate correlations between microstructure features and edge."""
    if len(coin_data) < 3:
        return {}

    features = ["trades_per_sec", "atr_pct", "volume_24h_usd", "avg_trade_size"]
    targets = ["mfe_mae_ratio", "net_taker", "has_edge"]

    correlations = {}
    for feature in features:
        for target in targets:
            values = [(d.get(feature, 0), d.get(target, 0)) for d in coin_data if feature in d and target in d]
            if len(values) >= 3:
                x, y = zip(*values)
                if np.std(x) > 0 and np.std(y) > 0:
                    r = np.corrcoef(x, y)[0, 1]
                    correlations[f"{feature}_vs_{target}"] = round(r, 3)

    return correlations


def determine_tier_thresholds(coin_data: List[Dict], correlations: Dict) -> Dict:
    """Determine optimal thresholds for each tier based on correlations."""
    # Separate coins with edge and without edge
    edge_coins = [d for d in coin_data if d.get("has_edge", False)]

    if not edge_coins:
        return {}

    # Calculate percentiles for edge coins
    def get_range(values, margin=0.1):
        if not values:
            return (0, 100)
        low = np.percentile(values, 10) * (1 - margin)
        high = np.percentile(values, 90) * (1 + margin)
        return (round(low, 3), round(high, 3))

    # TIER_1: Coins with edge
    tier1_density = get_range([d.get("trades_per_sec", 0) for d in edge_coins])
    tier1_volume = get_range([d.get("volume_24h_usd", 0) for d in edge_coins])

    return {
        "TIER_1": {
            "trade_density": tier1_density,
            "volume_24h": tier1_volume,
            "description": "Edge exists, moderate flow",
        },
        "TIER_2": {
            "trade_density": (tier1_density[1], tier1_density[1] * 2),
            "volume_24h": (tier1_volume[1], tier1_volume[1] * 3),
            "description": "Marginal edge, higher flow",
        },
        "TIER_3": {
            "trade_density": (tier1_density[1] * 2, 100),
            "volume_24h": (tier1_volume[1] * 3, 1_000_000_000_000),
            "description": "No edge, too efficient",
        },
    }


def generate_profiles_config(profiles: Dict, correlations: Dict, coin_data: List[Dict]) -> str:
    """Generate Python config file content."""
    lines = [
        '"""',
        "Auto-generated Coin Profiles by Profile Auditor",
        "Based on analysis of 10 coins × 24h historical data",
        '"""',
        "",
        "# Correlations between microstructure and edge",
        f"CORRELATIONS = {json.dumps(correlations, indent=4)}",
        "",
        "# Tier thresholds (auto-calibrated)",
        f"TIER_THRESHOLDS = {json.dumps(profiles, indent=4)}",
        "",
        "# Coin assignments (auto-detected from historical data)",
        "COIN_ASSIGNMENTS = {",
    ]

    for d in coin_data:
        symbol = d.get("symbol", "UNKNOWN")
        tier = "TIER_1" if d.get("has_edge") else "TIER_3"
        lines.append(f'    "{symbol}": "{tier}",')

    lines.append("}")
    lines.append("")
    lines.append("# Profile multipliers")
    lines.append("TIER_MULTIPLIERS = {")
    lines.append('    "TIER_1": {"tp": 1.0, "sl": 1.0, "quality_bonus": 0.1},')
    lines.append('    "TIER_2": {"tp": 0.8, "sl": 0.8, "quality_bonus": 0.0},')
    lines.append('    "TIER_3": {"tp": 0.5, "sl": 0.5, "quality_penalty": -0.2},')
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Profile Auditor — Calibrate coin tiers from historical data")
    parser.add_argument("--db", default="data/historian.db", help="Database path")
    parser.add_argument("--output", default="config/coin_profiles.py", help="Output config file")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    # Get all coins
    coins = conn.execute("SELECT DISTINCT symbol FROM signals").fetchall()
    symbols = [c[0] for c in coins]

    print(f"📊 Profile Auditor: Analyzing {len(symbols)} coins...")
    print()

    # Analyze each coin
    coin_data = []
    for symbol in symbols:
        print(f"  Analyzing {symbol}...")

        # Microstructure
        micro = analyze_coin_microstructure(conn, symbol)
        if not micro:
            print(f"  ⚠️ {symbol}: Insufficient data")
            continue

        # Edge
        edge = analyze_coin_edge(conn, symbol)

        # Combine
        data = {**micro, **edge}
        coin_data.append(data)

        edge_flag = "✅" if edge.get("has_edge") else "❌"
        print(
            f"  {edge_flag} {symbol}: MFE/MAE={edge.get('mfe_mae_ratio', 0):.2f}, "
            f"Net Taker={edge.get('net_taker', 0):+.4f}%, "
            f"Trades/sec={micro.get('trades_per_sec', 0):.1f}"
        )

    print()

    # Calculate correlations
    correlations = calculate_correlations(coin_data)
    print("📊 Correlations:")
    for key, val in sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"  {key}: {val}")

    print()

    # Determine tier thresholds
    profiles = determine_tier_thresholds(coin_data, correlations)
    print("📊 Tier Thresholds:")
    for tier, config in profiles.items():
        print(f"  {tier}: {config}")

    print()

    # Generate config file
    config_content = generate_profiles_config(profiles, correlations, coin_data)
    with open(args.output, "w") as f:
        f.write(config_content)
    print(f"✅ Generated {args.output}")

    conn.close()


if __name__ == "__main__":
    main()
