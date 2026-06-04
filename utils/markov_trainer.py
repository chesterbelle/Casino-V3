#!/usr/bin/env python3
"""
============================================
🎯 MARKOV TRAINER — Regime Transition Matrix
============================================

Calibrates a 3x3 Markov transition matrix from historical candle data.
Scans ALL datasets in data/datasets/backtest_ready/*.db to build a
generic crypto futures regime model (reduces overfitting).

Run manually every few weeks/months as market regimes evolve.

Usage:
    python utils/markov_trainer.py
    python utils/markov_trainer.py --threshold 0.001  # 0.1% instead of 0.05%
    python utils/markov_trainer.py --output config/markov_v2.json
"""

import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

DATASETS_DIR = os.path.join(PROJECT_ROOT, "data", "datasets", "backtest_ready")
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "config", "markov_transition.json")
DEFAULT_THRESHOLD = 0.0005  # 0.05% return = BALANCE

# ANSI Colors
CYAN = "\033[96m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def load_closes(db_path: str) -> list:
    """Extract close prices from a database file."""
    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
        cursor.execute("SELECT close FROM price_candles ORDER BY timestamp")
        closes = [r[0] for r in cursor.fetchall()]
        db.close()
        return closes
    except Exception as e:
        print(f"  {RED}Error loading {os.path.basename(db_path)}: {e}{RESET}")
        return []


def classify_returns(closes: list, threshold: float) -> list:
    """Classify each candle into BALANCE/UP/DOWN based on return."""
    if len(closes) < 2:
        return []

    states = ["BALANCE"]  # First candle has no return
    for i in range(1, len(closes)):
        ret = (closes[i] - closes[i - 1]) / closes[i - 1]
        if abs(ret) < threshold:
            states.append("BALANCE")
        elif ret > 0:
            states.append("UP")
        else:
            states.append("DOWN")
    return states


def count_transitions(states: list) -> dict:
    """Count transitions between regime states."""
    STATES = ["BALANCE", "UP", "DOWN"]
    raw = {s: {ns: 0 for ns in STATES} for s in STATES}
    for i in range(1, len(states)):
        raw[states[i - 1]][states[i]] += 1
    return raw


def normalize(raw: dict) -> dict:
    """Normalize raw counts to probabilities."""
    STATES = ["BALANCE", "UP", "DOWN"]
    normalized = {}
    for s in STATES:
        total = sum(raw[s].values())
        normalized[s] = {}
        for ns in STATES:
            normalized[s][ns] = round(raw[s][ns] / total, 4) if total > 0 else 0.0
    return normalized


def main():
    parser = argparse.ArgumentParser(description="Markov Regime Trainer")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Return threshold for BALANCE (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  🎯 MARKOV TRAINER — Regime Transition Matrix{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")

    # Scan all datasets
    db_files = sorted(glob.glob(os.path.join(DATASETS_DIR, "*.db")))
    if not db_files:
        print(f"{RED}No databases found in {DATASETS_DIR}{RESET}")
        sys.exit(1)

    print(f"{BOLD}Scanning {len(db_files)} datasets...{RESET}\n")

    all_states = []
    dataset_stats = []
    total_candles = 0

    for db_path in db_files:
        name = os.path.basename(db_path)
        closes = load_closes(db_path)
        if not closes:
            continue

        states = classify_returns(closes, args.threshold)
        all_states.extend(states)
        total_candles += len(closes)

        # Stats per dataset
        bal = states.count("BALANCE")
        up = states.count("UP")
        down = states.count("DOWN")
        dataset_stats.append(
            {
                "name": name,
                "candles": len(closes),
                "BALANCE": bal,
                "UP": up,
                "DOWN": down,
            }
        )

        print(f"  {name}: {len(closes):,} candles → B:{bal} U:{up} D:{down}")

    if not all_states:
        print(f"\n{RED}No data loaded. Exiting.{RESET}")
        sys.exit(1)

    # Aggregate statistics
    raw = count_transitions(all_states)
    matrix = normalize(raw)

    total_bal = all_states.count("BALANCE")
    total_up = all_states.count("UP")
    total_down = all_states.count("DOWN")
    total_transitions = len(all_states) - 1

    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  RESULTS{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")

    print(f"  {BOLD}Datasets:{RESET}       {len(dataset_stats)}")
    print(f"  {BOLD}Total candles:{RESET}  {total_candles:,}")
    print(f"  {BOLD}Transitions:{RESET}    {total_transitions:,}")
    print(f"  {BOLD}Threshold:{RESET}      {args.threshold} ({args.threshold*100:.2f}%)")

    print(f"\n  {BOLD}State Distribution:{RESET}")
    print(f"    BALANCE: {total_bal:,} ({total_bal/len(all_states)*100:.1f}%)")
    print(f"    UP:      {total_up:,} ({total_up/len(all_states)*100:.1f}%)")
    print(f"    DOWN:    {total_down:,} ({total_down/len(all_states)*100:.1f}%)")

    print(f"\n  {BOLD}Transition Matrix:{RESET}")
    print(f"    {'From/To':>10} {'BALANCE':>10} {'UP':>10} {'DOWN':>10}")
    for s in ["BALANCE", "UP", "DOWN"]:
        row = matrix[s]
        print(f"    {s:>10} {row['BALANCE']:>10.4f} {row['UP']:>10.4f} {row['DOWN']:>10.4f}")

    # Persistence: how sticky each state is
    print(f"\n  {BOLD}Persistence (P(same state)):{RESET}")
    for s in ["BALANCE", "UP", "DOWN"]:
        sticky = matrix[s][s]
        label = "very sticky" if sticky > 0.7 else "moderate" if sticky > 0.5 else "volatile"
        print(f"    {s}: {sticky:.4f} ({label})")

    # Save
    output = {
        "meta": {
            "states": ["BALANCE", "UP", "DOWN"],
            "trained": True,
            "trained_at": datetime.now().isoformat(),
            "datasets": len(dataset_stats),
            "total_candles": total_candles,
            "total_transitions": total_transitions,
            "return_threshold": args.threshold,
        },
        "transitions": matrix,
        "raw_counts": raw,
        "state_distribution": {
            "BALANCE": total_bal,
            "UP": total_up,
            "DOWN": total_down,
        },
        "dataset_stats": dataset_stats,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  {GREEN}✅ Saved to {args.output}{RESET}\n")


if __name__ == "__main__":
    main()
