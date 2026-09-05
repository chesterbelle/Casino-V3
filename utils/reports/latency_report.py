import argparse
import os
import sqlite3
import sys
from datetime import datetime

import numpy as np


class LatencyReporter:
    def __init__(self, db_path=None):
        if db_path is None:
            if os.path.exists("data/historian.db"):
                self.db_path = "data/historian.db"
            else:
                self.db_path = "data/casino_v3.db"
        else:
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
                        t0_market_ingress_ts, t1_pattern_signal_ts, t2_order_dispatch_ts, t3_exchange_ack_ts, t4_order_fill_ts,
                        t0_signal_ts, t1_decision_ts, t2_submit_ts,
                        latency_t0_t1_ms, latency_t1_t2_ms, latency_t2_t3_ms, latency_t3_t4_ms, latency_total_ms,
                        slippage_pct
                    FROM trades
                    WHERE (t0_market_ingress_ts IS NOT NULL OR t0_signal_ts IS NOT NULL)
                """
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"❌ Error querying database: {e}")
            return []

    def generate_report(self):
        data = self.get_latency_data()
        if not data:
            print("No latency data found in trades table.")
            return

        print(f"\n⚡ 5-POINT MICRO-TELEMETRY REPORT ({len(data)} trades)")
        print("=" * 105)
        print(
            f"{'Trade ID':<15} {'Symbol':<10} {'ΔT01 (ms)':<12} {'ΔT12 (ms)':<12} {'ΔT23 (ms)':<12} {'ΔT34 (ms)':<12} {'Total (ms)':<12} {'Slippage %':<10}"
        )
        print("-" * 105)

        stats = {"dt01": [], "dt12": [], "dt23": [], "dt34": [], "total": []}

        for row in data:
            t0 = row["t0_market_ingress_ts"] or row["t0_signal_ts"]
            t1 = row["t1_pattern_signal_ts"] or row["t1_decision_ts"]
            t2 = row["t2_order_dispatch_ts"] or row["t2_submit_ts"]
            t3 = row["t3_exchange_ack_ts"]
            t4 = row["t4_order_fill_ts"]

            dt01 = (t1 - t0) * 1000.0 if (t0 and t1 and t1 >= t0) else None
            dt12 = (t2 - t1) * 1000.0 if (t1 and t2 and t2 >= t1) else None
            dt23 = (t3 - t2) * 1000.0 if (t2 and t3 and t3 >= t2) else None
            dt34 = (t4 - t3) * 1000.0 if (t3 and t4 and t4 >= t3) else None
            dt_tot = (t4 - t0) * 1000.0 if (t0 and t4 and t4 >= t0) else None

            slippage = row["slippage_pct"] or 0.0

            if dt01 is not None:
                stats["dt01"].append(dt01)
            if dt12 is not None:
                stats["dt12"].append(dt12)
            if dt23 is not None:
                stats["dt23"].append(dt23)
            if dt34 is not None:
                stats["dt34"].append(dt34)
            if dt_tot is not None:
                stats["total"].append(dt_tot)

            str_dt01 = f"{dt01:12.2f}" if dt01 is not None else f"{'N/A':>12}"
            str_dt12 = f"{dt12:12.2f}" if dt12 is not None else f"{'N/A':>12}"
            str_dt23 = f"{dt23:12.2f}" if dt23 is not None else f"{'N/A':>12}"
            str_dt34 = f"{dt34:12.2f}" if dt34 is not None else f"{'N/A':>12}"
            str_tot = f"{dt_tot:12.2f}" if dt_tot is not None else f"{'N/A':>12}"

            print(
                f"{str(row['trade_id'])[:15]:<15} {row['symbol']:<10} {str_dt01} {str_dt12} {str_dt23} {str_dt34} {str_tot} {slippage:10.4f}"
            )

        print("=" * 105)
        print("AST (5-POINT AVERAGE SYSTEM TELEMETRY)")
        print("-" * 60)

        def _fmt(arr):
            if not arr:
                return "N/A"
            return f"Avg: {np.mean(arr):6.1f}ms | P95: {np.percentile(arr, 95):6.1f}ms | Min: {np.min(arr):6.1f}ms | Max: {np.max(arr):6.1f}ms"

        print(f"ΔT01 (Pattern Formation T0->T1): {_fmt(stats['dt01'])}")
        print(f"ΔT12 (Signal-to-Wire   T1->T2): {_fmt(stats['dt12'])}")
        print(f"ΔT23 (Network RTT/Ack  T2->T3): {_fmt(stats['dt23'])}")
        print(f"ΔT34 (Matching Fill    T3->T4): {_fmt(stats['dt34'])}")
        print(f"ΔT_total (End-to-End   T0->T4): {_fmt(stats['total'])}")
        print("=" * 105)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Casino-V3 5-Point Latency Report")
    parser.add_argument("--db", type=str, default=None, help="Path to database")
    args = parser.parse_args()

    reporter = LatencyReporter(args.db)
    reporter.generate_report()
