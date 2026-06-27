#!/usr/bin/env python3
"""
Benchmark script to compare UNION ALL vs Pandas concat approach.
Tests the performance improvement on a real dataset.
"""

import asyncio
import sys
import time
from pathlib import Path

import aiosqlite
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def benchmark_union_all(db_path: str, symbol: str, window_start: float, window_end: float):
    """Benchmark UNION ALL approach."""
    start = time.time()

    async with aiosqlite.connect(db_path) as db:
        union_query = """
            SELECT timestamp, 0 as event_type, bids, asks, NULL as price, NULL as volume, NULL as side
            FROM depth_snapshots
            WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
            UNION ALL
            SELECT timestamp, 1 as event_type, NULL, NULL, price, amount, side
            FROM market_trades
            WHERE symbol = ? AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
        """
        params = (symbol, window_start, window_end, symbol, window_start, window_end)

        cursor = await db.execute(union_query, params)
        count = 0
        while True:
            rows = await cursor.fetchmany(10000)
            if not rows:
                break
            count += len(rows)

    elapsed = time.time() - start
    print(f"UNION ALL: {count} events in {elapsed:.2f}s ({count/elapsed:.0f} events/s)")
    return elapsed, count


async def benchmark_pandas_concat(db_path: str, symbol: str, window_start: float, window_end: float):
    """Benchmark Pandas concat approach (original)."""
    start = time.time()

    async with aiosqlite.connect(db_path) as db:
        # Fetch Depth
        cursor = await db.execute(
            "SELECT timestamp, 'DEPTH' as event_type, bids, asks FROM depth_snapshots WHERE symbol = ? AND timestamp >= ? AND timestamp < ?",
            (symbol, window_start, window_end),
        )
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        depth_df = pd.DataFrame(rows, columns=columns)

        # Fetch Trades
        cursor = await db.execute(
            "SELECT timestamp, 'TICK' as event_type, price, amount as volume, side FROM market_trades WHERE symbol = ? AND timestamp >= ? AND timestamp < ?",
            (symbol, window_start, window_end),
        )
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        trades_df = pd.DataFrame(rows, columns=columns)

        # Concat and sort (the bottleneck)
        window_df = pd.concat([depth_df, trades_df], ignore_index=True)
        window_df = window_df.sort_values("timestamp").reset_index(drop=True)
        count = len(window_df)

    elapsed = time.time() - start
    print(f"Pandas:    {count} events in {elapsed:.2f}s ({count/elapsed:.0f} events/s)")
    return elapsed, count


async def main():
    # Test dataset
    db_path = "data/datasets/daily_backtest_ready/ADAUSDT_BALANCE_2025-11-01.db"
    symbol = "ADAUSDT"

    print("📊 Benchmarking backtest feed performance...")
    print(f"Dataset: {db_path}")
    print()

    # Get time range
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM depth_snapshots WHERE symbol = ?", (symbol,)
        )
        row = await cursor.fetchone()
        min_ts, max_ts = row

    # Test with 1 hour window
    window_start = min_ts
    window_end = min_ts + 3600

    print("Testing 1-hour window...")
    print("-" * 50)

    # Warmup
    print("Warmup...")
    await benchmark_union_all(db_path, symbol, window_start, window_end)

    # Benchmark UNION ALL
    print("\nUNION ALL (3 runs):")
    union_times = []
    for i in range(3):
        elapsed, count = await benchmark_union_all(db_path, symbol, window_start, window_end)
        union_times.append(elapsed)

    # Benchmark Pandas
    print("\nPandas concat (3 runs):")
    pandas_times = []
    for i in range(3):
        elapsed, count = await benchmark_pandas_concat(db_path, symbol, window_start, window_end)
        pandas_times.append(elapsed)

    # Results
    print()
    print("=" * 50)
    print("RESULTS")
    print("=" * 50)
    avg_union = sum(union_times) / len(union_times)
    avg_pandas = sum(pandas_times) / len(pandas_times)
    speedup = avg_pandas / avg_union
    improvement = ((avg_pandas - avg_union) / avg_pandas) * 100

    print(f"UNION ALL avg: {avg_union:.2f}s")
    print(f"Pandas avg:    {avg_pandas:.2f}s")
    print(f"Speedup:       {speedup:.1f}x faster")
    print(f"Improvement:   {improvement:.1f}%")
    print()

    # Extrapolate to full month
    estimated_union = (max_ts - min_ts) / 3600 * avg_union
    estimated_pandas = (max_ts - min_ts) / 3600 * avg_pandas

    print("Extrapolated for full month dataset:")
    print(f"UNION ALL: {estimated_union/3600:.1f} hours")
    print(f"Pandas:    {estimated_pandas/3600:.1f} hours")
    print(f"Time saved: {(estimated_pandas - estimated_union)/3600:.1f} hours")


if __name__ == "__main__":
    asyncio.run(main())
