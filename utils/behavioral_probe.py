#!/usr/bin/env python3
"""
=============================================================
🧬 BEHAVIORAL PROBE — Asset DNA Extractor
=============================================================

This tool analyzes signal trajectories to quantify the behavioral
dynamics of an asset, moving beyond static book density metrics.

Metrics:
  - Eff_abs (Absorption Efficiency): % of absorptions that result in reversal.
  - Vel_rev (Reversal Velocity): Average time to reach reversal target.
  - Pers_brk (Breakout Persistence): % of 'failed breakouts' that are real moves.

Output: data/behavioral_profiles.json
"""

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from utils.trajectory_core import SETUP_WINDOWS, get_trajectory, load_data

# --- Configuration ---
REVERSAL_TARGET_PCT = 0.20  # MFE required to count as a successful reversal
REVERSAL_STOP_PCT = 0.20  # MAE that invalidates a reversal
BREAKOUT_TARGET_PCT = 0.25  # MFE required to count as a persistent move
BREAKOUT_STOP_PCT = 0.15  # MAE that invalidates a persistent move


def analyze_behavior(db_path: str):
    """Analyzes a single database file and returns behavior metrics for its symbols."""
    try:
        signals, prices, _ = load_data(db_path)
        if signals.empty:
            return {}
    except Exception as e:
        print(f"  ⚠️ Error loading {db_path}: {e}")
        return {}

    symbols = signals["symbol"].unique()
    local_profiles = {}

    for symbol in symbols:
        coin_signals = signals[signals["symbol"] == symbol]

        # --- 1. Absorption Efficiency & Velocity ---
        abs_signals = coin_signals[coin_signals["setup_type"] == "tactical_absorption"]
        abs_wins = 0
        abs_times = []

        for _, sig in abs_signals.iterrows():
            traj = get_trajectory(sig, prices, SETUP_WINDOWS.get("tactical_absorption", 21600))
            if traj.empty:
                continue

            target_mask = traj["mfe_pct"] >= REVERSAL_TARGET_PCT
            if target_mask.any():
                first_hit_idx = traj[target_mask].index[0]
                mae_before_hit = traj.loc[:first_hit_idx, "mae_pct_so_far"].max()
                if mae_before_hit < REVERSAL_STOP_PCT:
                    abs_wins += 1
                    abs_times.append(traj.loc[first_hit_idx, "elapsed_seconds"])

        eff_abs = abs_wins / len(abs_signals) if len(abs_signals) > 0 else None
        vel_rev = np.mean(abs_times) if abs_times else None

        # --- 2. Breakout Persistence ---
        brk_signals = coin_signals[coin_signals["setup_type"] == "failed_breakout"]
        brk_wins = 0

        for _, sig in brk_signals.iterrows():
            traj = get_trajectory(sig, prices, SETUP_WINDOWS.get("failed_breakout", 21600))
            if traj.empty:
                continue

            target_mask = traj["mfe_pct"] >= BREAKOUT_TARGET_PCT
            if target_mask.any():
                first_hit_idx = traj[target_mask].index[0]
                mae_before_hit = traj.loc[:first_hit_idx, "mae_pct_so_far"].max()
                if mae_before_hit < BREAKOUT_STOP_PCT:
                    brk_wins += 1

        pers_brk = brk_wins / len(brk_signals) if len(brk_signals) > 0 else None

        local_profiles[symbol] = {
            "eff_abs": eff_abs,
            "vel_rev": vel_rev,
            "pers_brk": pers_brk,
            "n_abs": len(abs_signals),
            "n_brk": len(brk_signals),
        }

    return local_profiles


def process_all_datasets(dataset_dir: str):
    print(f"🧬 Scanning datasets in {dataset_dir}...")
    files = glob.glob(f"{dataset_dir}/*.db")
    if not files:
        print("❌ No .db files found in dataset directory.")
        return {}

    # Accumulator for metrics: { symbol: { metric: [values] } }
    aggregated = {}

    for f in files:
        filename = Path(f).name
        print(f"  📦 Processing {filename}...", end="\r")
        local_res = analyze_behavior(f)

        for symbol, metrics in local_res.items():
            if symbol not in aggregated:
                aggregated[symbol] = {"eff_abs": [], "vel_rev": [], "pers_brk": [], "n_abs": 0, "n_brk": 0}

            if metrics["eff_abs"] is not None:
                aggregated[symbol]["eff_abs"].append(metrics["eff_abs"])
            if metrics["vel_rev"] is not None:
                aggregated[symbol]["vel_rev"].append(metrics["vel_rev"])
            if metrics["pers_brk"] is not None:
                aggregated[symbol]["pers_brk"].append(metrics["pers_brk"])
            aggregated[symbol]["n_abs"] += metrics["n_abs"]
            aggregated[symbol]["n_brk"] += metrics["n_brk"]

    print(f"\n  ✅ Processed {len(files)} datasets. Aggregating results...")

    final_profiles = {}
    for symbol, data in aggregated.items():
        final_profiles[symbol] = {
            "eff_abs": float(np.mean(data["eff_abs"])) if data["eff_abs"] else 0.0,
            "vel_rev": float(np.mean(data["vel_rev"])) if data["vel_rev"] else 0.0,
            "pers_brk": float(np.mean(data["pers_brk"])) if data["pers_brk"] else 0.0,
            "n_abs": data["n_abs"],
            "n_brk": data["n_brk"],
        }

    return final_profiles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_dir", default="data/datasets/backtest_ready/", help="Directory with .db datasets")
    parser.add_argument("--db", default="data/historian.db", help="Fallback to single DB if dataset_dir is empty")
    parser.add_argument("--output", default="data/behavioral_profiles.json")
    args = parser.parse_args()

    try:
        # Try datasets first
        profiles = process_all_datasets(args.dataset_dir)

        # If no datasets worked, try the fallback DB
        if not profiles:
            print("⚠️ No data from datasets. Trying fallback historian DB...")
            profiles = analyze_behavior(args.db)

        if not profiles:
            print("❌ No behavioral data could be extracted.")
            return

        # Ensure output directory exists
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)

        with open(args.output, "w") as f:
            json.dump(profiles, f, indent=2)

        print(f"\n✅ Behavioral Profiles saved to {args.output}")

        # Print Summary
        print("\n" + "=" * 60)
        print(f"{'Symbol':<20} {'Eff_Abs':<10} {'Vel_Rev':<10} {'Pers_Brk':<10}")
        print("-" * 60)
        for sym, p in profiles.items():
            print(f"{sym:<20} {p['eff_abs']:<10.2%} {p['vel_rev']:<10.1f} {p['pers_brk']:<10.2%}")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
