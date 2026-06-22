#!/usr/bin/env python3
"""Monitor backtest progress in real-time."""

import time
from pathlib import Path

LOG_FILE = Path("logs/bt_SOL_monthly_2026_03.log")


def monitor():
    if not LOG_FILE.exists():
        print("❌ Log file not found: {LOG_FILE}")
        return

    print("📊 Monitoring backtest progress...")
    print("Log: {LOG_FILE.absolute()}")
    print("-" * 60)

    last_batch = 0
    last_time = time.time()

    try:
        with open(LOG_FILE, "r") as f:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(2)
                    continue

                if "Processing batch:" in line:
                    # Extract batch count
                    parts = line.split("Processing batch: ")[1].split(" events")
                    batch_size = int(parts[0])
                    last_batch += batch_size

                    now = time.time()
                    elapsed = now - last_time
                    if elapsed >= 10:  # Show stats every 10s
                        rate = batch_size / elapsed if elapsed > 0 else 0
                        print("⏳ Events: {last_batch:,} | Rate: {rate:,.0f} events/s")
                        last_time = now
                        last_batch = 0

                elif "TOTAL SIGNALS" in line or "Backtest Replay Finished" in line:
                    print("\n✅ {line.strip()}")
                    if "Finished" in line:
                        print("\n🏁 Backtest completed!")
                        return

    except KeyboardInterrupt:
        print("\n👋 Monitor stopped. Backtest still running.")
        print("Check log: tail -f {LOG_FILE}")


if __name__ == "__main__":
    monitor()
