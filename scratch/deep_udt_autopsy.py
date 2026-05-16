import json
import sqlite3
from collections import Counter


def run_deep_autopsy():
    conn = sqlite3.connect("data/historian.db")
    cursor = conn.execute('SELECT status, reason, metrics FROM decision_traces WHERE reason = "Phase 2 Timeout"')
    rows = cursor.fetchall()

    sensor_failures = Counter()

    for status, reason, metrics_json in rows:
        try:
            metrics = json.loads(metrics_json)
            # Check for sensors in duration_ms or other keys
            # In the guardian, we add the current state to metadata on timeout
            if "last_state" in metrics:
                state = metrics["last_state"]
                cvd_ok = state.get("cvd_ok", False)
                price_ok = state.get("price_ok", False)

                if not cvd_ok and not price_ok:
                    sensor_failures["BOTH_FAILED"] += 1
                elif not cvd_ok:
                    sensor_failures["CVD_FLIP_MISSING"] += 1
                elif not price_ok:
                    sensor_failures["PRICE_BREAK_MISSING"] += 1
        except Exception as e:
            continue

    print("\n" + "=" * 40)
    print("🔬 DEEP DNA ANALYSIS: PHASE 2 TIMEOUTS")
    print("=" * 40)
    print(f"Total Timeouts Analyzed: {len(rows)}")
    print("-" * 20)
    print("SENSOR BOTTLENECKS:")
    for sensor, count in sensor_failures.most_common():
        print(f"  {count:3} | {sensor} ({count/len(rows):.1%})")

    conn.close()


if __name__ == "__main__":
    run_deep_autopsy()
