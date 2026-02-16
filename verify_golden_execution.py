import asyncio
import logging
import os
import sys
import time

# Add project root to path
sys.path.append(os.getcwd())

from exchanges.connectors.binance.binance_native_connector import (  # noqa: E402
    BinanceNativeConnector,
)

# Mock keys if needed to prevent crash, though connector usually handles empty keys for public data if logic permits
# But BinanceNativeConnector logs warning and continues.
os.environ["BINANCE_API_KEY"] = "dummy"
os.environ["BINANCE_SECRET"] = "dummy"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


async def main():
    print("--- Golden Execution Verification ---")

    # Initialize Connector with empty keys to force Public-Only mode
    # This avoids signed request failures (Position Mode, User Stream)
    connector = BinanceNativeConnector(mode="live", api_key="", secret="")
    # Bypass key check if needed, but the class warns and proceeds for public data usually.
    # We fake the keys above.

    try:
        await connector.connect()

        symbol = "BTC/USDT:USDT"
        print(f"Subscribing to {symbol} via WatchOrderBook (Golden Path)...")

        # Trigger subscription
        # This will call subscribe_depth -> @depth5@100ms
        await connector.watch_order_book(symbol)

        print("Waiting for cache warm-up...")
        cached = None
        for i in range(50):
            cached = connector.get_cached_order_book(symbol)
            if cached:
                print(f"✅ Cache WARMED UP at tick {i}")
                print(f"   Timestamp: {cached.get('timestamp')}")
                print(f"   Bids: {len(cached.get('bids', []))} | Asks: {len(cached.get('asks', []))}")
                break
            await asyncio.sleep(0.1)

        if not cached:
            print("❌ FAIL: Cache did not warm up.")
            return

        # Measure Access Latency (Sync)
        print("\nMeasuring 10,000 Cache Accesses...")
        start = time.time()
        for _ in range(10000):
            _ = connector.get_cached_order_book(symbol)
        end = time.time()

        total_time_ms = (end - start) * 1000
        avg_latency_us = (total_time_ms / 10000) * 1000

        print(f"Total Time: {total_time_ms:.4f} ms")
        print(f"Avg Latency: {avg_latency_us:.4f} µs (Microseconds)")

        if avg_latency_us < 50:  # Expecting < 50us (it's a dict lookup)
            print("✅ PASS: Zero-Latency Access Confirmed (< 50µs)")
        else:
            print(f"⚠️ WARNING: Latency higher than expected ({avg_latency_us:.2f}µs)")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await connector.close()
        print("Connector closed.")


if __name__ == "__main__":
    asyncio.run(main())
