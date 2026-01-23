import argparse
import os
import sqlite3
import sys
from datetime import datetime


class LatencyReporter:
    def __init__(self, db_path="data/casino_v3.db"):
        self.db_path = db_path

    def get_latency_data(self):
        if not os.path.exists(self.db_path):
            print(f"❌ Database not found at {self.db_path}")
            return []

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT
                        trade_id, symbol, timestamp,
                        t0_signal_ts, t2_submit_ts, t4_fill_ts, slippage_pct
                    FROM trades
                    WHERE t0_signal_ts IS NOT NULL
                """
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"❌ Error querying database: {e}")
            return []

    def generate_report(self):
        data = self.get_latency_data()
        if not data:
            print("No latency data found (t0_signal_ts IS NULL for all trades or no trades).")
            return

        print(f"\n📊 LATENCY TELEMETRY REPORT ({len(data)} trades)")
        print("=" * 80)
        print(
            f"{'Trade ID':<15} {'Symbol':<10} {'Sig->Sub (ms)':<15} {'Sub->Fill (ms)':<15} {'Total (ms)':<12} {'Slippage %':<10}"
        )
        print("-" * 80)

        stats = {"sig_sub": [], "sub_fill": [], "total": []}

        for row in data:
            t0 = row["t0_signal_ts"]
            t2 = row["t2_submit_ts"]
            t4 = row["t4_fill_ts"]

            # Validity checks
            if not (t0 and t2 and t4):
                print(f"{row['trade_id'][:15]:<15} {row['symbol']:<10} {'INCOMPLETE':<40}")
                continue

            # Calculate Deltas (ms)
            sig_sub_ms = (t2 - t0) * 1000
            sub_fill_ms = (t4 - t2) * 1000
            total_ms = (t4 - t0) * 1000

            slippage = row["slippage_pct"] or 0.0

            stats["sig_sub"].append(sig_sub_ms)
            stats["sub_fill"].append(sub_fill_ms)
            stats["total"].append(total_ms)

            print(
                f"{row['trade_id'][:15]:<15} {row['symbol']:<10} {sig_sub_ms:15.2f} {sub_fill_ms:15.2f} {total_ms:12.2f} {slippage:10.4f}"
            )

        if stats["total"]:
            print("=" * 80)
            print("AST (AVERAGE SYSTEM TELEMETRY)")
            print("-" * 30)
            avg_sig_sub = sum(stats["sig_sub"]) / len(stats["sig_sub"])
            avg_sub_fill = sum(stats["sub_fill"]) / len(stats["sub_fill"])
            avg_total = sum(stats["total"]) / len(stats["total"])

            print(f"Signal -> Submit (Internal): {avg_sig_sub:.2f} ms")
            print(f"Submit -> Fill (External):   {avg_sub_fill:.2f} ms")
            print(f"Total End-to-End Latency:    {avg_total:.2f} ms")
            print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Casino-V3 Latency Report")
    parser.add_argument("--db", type=str, default="data/casino_v3.db", help="Path to database")
    args = parser.parse_args()

    reporter = LatencyReporter(args.db)
    reporter.generate_report()
