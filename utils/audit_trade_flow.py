"""
Trade Flow Auditor (Phase 260)
Reads historian.db to determine Execution Hygiene based on Event Sourcing.
"""

import argparse
import os
import sqlite3
import sys
from collections import defaultdict


def audit_trade_flow(db_path: str):
    if not os.path.exists(db_path):
        print(f"❌ Error: Database not found at {db_path}")
        return False

    print(f"\n🔍 Auditing Trade Flow: {db_path}")
    print("=" * 50)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Fetch all events
        cursor.execute(
            "SELECT trade_id, timestamp, event_type, details FROM trade_lifecycle_events ORDER BY timestamp ASC"
        )
        events = cursor.fetchall()

        # Unique trade IDs from events (filtering out system events like RECON_WORKER)
        all_trades = list(set([row["trade_id"] for row in events if row["trade_id"].startswith("CASINO_ENTRY")]))

        # Cross check with trades table just for total count reference
        cursor.execute("SELECT COUNT(DISTINCT trade_id) FROM trades")
        db_trades_count = cursor.fetchone()[0]

        conn.close()
        print(f"ℹ️  Reference: {db_trades_count} trade_ids en tabla trades")
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

    trade_events = defaultdict(list)
    for row in events:
        trade_events[row["trade_id"]].append(row["event_type"])

    clean = 0
    healed = 0
    force_closed = 0
    unknown = 0

    force_closed_ids = []

    for trade_id in all_trades:
        flow = trade_events.get(trade_id, [])
        if not flow:
            unknown += 1
            continue

        if "RECON_FORCE_CLOSE" in flow:
            force_closed += 1
            force_closed_ids.append(trade_id)
        elif "OCO_FAILED" in flow or "RECON_WAKEUP" in flow or "RECON_HEALED" in flow:
            healed += 1
        else:
            # Assume clean if it made it without failures/force closes
            clean += 1

    total = len(all_trades)

    if total == 0:
        print("⚠️ No trades found in database.")
        return True

    print(f"📊 TRADE FLOW HYGIENE AUDIT")
    print(f"Total Trades Evaluados: {total}")
    print("-" * 50)
    print(f"🟢 Clean Executions:   {clean:4d}  ({(clean/total)*100:.1f}%)")
    print(f"🟡 Recon Healed:       {healed:4d}  ({(healed/total)*100:.1f}%)")
    print(f"🔴 Force Closed (Poor Execution): {force_closed:4d}  ({(force_closed/total)*100:.1f}%)")

    if unknown > 0:
        print(f"⚪ Unknown (Legacy/No events): {unknown:4d}  ({(unknown/total)*100:.1f}%)")

    print("=" * 50)

    if force_closed > 0:
        print("❌ VERDICT: FAIL")
        print("   ↳ Se detectaron trades con ejecución pobre (Force Closed):")
        for tid in force_closed_ids[:5]:
            print(f"      - {tid}")
        if len(force_closed_ids) > 5:
            print(f"      - ... y {len(force_closed_ids) - 5} más.")
        return False
    else:
        print("✅ VERDICT: PASS (Ejecución Higiénica 100%)")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audits trade lifecycle events to measure execution hygiene.")
    parser.add_argument("--db", type=str, default="data/historian.db", help="Path to historian.db")
    args = parser.parse_args()

    success = audit_trade_flow(args.db)
    sys.exit(0 if success else 1)
