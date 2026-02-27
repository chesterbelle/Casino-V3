"""
Statistical Log Auditor - Phase 300
-----------------------------------
Parses Stress Test logs and extracts health metrics beyond simple PASS/FAIL.
Detects: Trade Inflation, Exchange Error Spikes, Ghost Removals.
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path


def audit_log(log_path: str):
    path = Path(log_path)
    if not path.exists():
        print(f"❌ Error: File not found {log_path}")
        return False

    content = path.read_text()

    print(f"\n🔍 Auditing Log: {log_path}")
    print("-" * 50)

    # 1. Component Extraction (V3 Specific)
    signals = len(re.findall(r"📡 Aggregated Signal", content))
    trades = len(re.findall(r"💾 Historian: Queued trade", content))
    ghost_removals = len(re.findall(r"Analyzing Ghost Position", content))
    unmatched = len(re.findall(r"WS Event UNMATCHED", content))
    shadow_sl_triggers = len(re.findall(r"🚨 Shadow SL Triggered", content))

    # 2. Exchange Errors (-XXXX codes)
    error_codes = re.findall(r"\((-?\d{4})\)", content)
    error_counts = Counter(error_codes)

    # 3. Efficiency Ratio
    ratio = trades / signals if signals > 0 else 0

    print(f"📊 Strategy Signals:  {signals}")
    print(f"📊 Actual Trades:     {trades}")
    print(f"⚖️ Efficiency Ratio:  {ratio:.2f} (Target < 1.5)")
    print(f"🔥 Shadow SL Hits:     {shadow_sl_triggers}")
    print(f"👻 Ghost Removals:    {ghost_removals} (Target: 0)")
    print(f"❌ Unmatched Events:  {unmatched} (Target: 0)")

    if error_counts:
        print("\n🚫 Exchange Errors detected:")
        for code, count in error_counts.items():
            desc = "Min Notional / Zero Quantity" if code == "-4003" else "Other"
            print(f"   • {code}: {count} occurrences ({desc})")

    # 4. Final Verdict
    print("-" * 50)
    failures = []

    if signals > 0 and ratio > 1.5:
        failures.append(f"Trade Inflation! Ratio {ratio:.2f} > 1.5")
    if ghost_removals > 0:
        failures.append(f"Structural Flaw! {ghost_removals} ghosts removed")
    if unmatched > 0:
        failures.append(f"Integrity Loss! {unmatched} events unmatched")
    if "-4003" in error_counts:
        failures.append(f"Fatal Configuration! {error_counts['-4003']} zero-quantity errors detected")

    if failures:
        print("❌ VERDICT: FAIL")
        for f in failures:
            print(f"   ↳ {f}")
        return False
    else:
        print("✅ VERDICT: PASS (Stable & Efficient)")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("log_file", help="Path to the log file to audit")
    args = parser.parse_args()

    success = audit_log(args.log_file)
    sys.exit(0 if success else 1)
