import json
import sqlite3
from collections import Counter


def run_autopsy():
    conn = sqlite3.connect("data/historian.db")
    cursor = conn.execute("SELECT status, reason, metrics FROM decision_traces")
    rows = cursor.fetchall()

    status_counts = Counter()
    reason_counts = Counter()

    for status, reason, metrics_json in rows:
        status_counts[status] += 1
        if status != "EXECUTED":
            reason_counts[reason] += 1

    print("\n" + "=" * 40)
    print("🧬 UDT FORENSIC AUTOPSY REPORT")
    print("=" * 40)
    print(f"Total Traces: {len(rows)}")
    print("-" * 20)
    print("OUTCOMES:")
    for status, count in status_counts.items():
        print(f"  {status:12}: {count} ({count/len(rows):.1%})")

    print("-" * 20)
    print("FAILURE REASONS (DISCARDED/PENDING):")
    # Sort by count
    for reason, count in reason_counts.most_common():
        print(f"  {count:3} | {reason}")

    conn.close()


if __name__ == "__main__":
    run_autopsy()
