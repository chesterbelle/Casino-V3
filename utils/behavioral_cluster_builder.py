#!/usr/bin/env python3
"""
=============================================================
🧬 BEHAVIORAL CLUSTER BUILDER — DNA-Based Taxonomy
=============================================================

This builder replaces static book metrics with Behavioral DNA
(Eff_abs, Vel_rev, Pers_brk) to group assets by auction dynamics.

Goal: Separate assets that 'look' similar but 'behave' differently
(e.g., XRP vs DOGE).
"""

import argparse
import json
import math
import random
from pathlib import Path
from typing import Dict, List, Tuple

# --- Constants ---
PROFILES_PATH = Path("data/behavioral_profiles.json")
OUTPUT_PATH = Path("config/clusters_fixed.json")

from utils.cluster_constants import BEHAVIORAL_NORM_MAX, BEHAVIORAL_NORM_MIN

# Normalization bounds for behavioral metrics
NORM_MIN = BEHAVIORAL_NORM_MIN
NORM_MAX = BEHAVIORAL_NORM_MAX


def _euclidean_distance(a: dict, b: dict) -> float:
    keys = set(a.keys()) & set(b.keys())
    if not keys:
        return float("inf")
    return math.sqrt(sum((a.get(k, 0) - b.get(k, 0)) ** 2 for k in keys))


def _normalize(metrics: dict) -> dict:
    normalized = {}
    for key, value in metrics.items():
        if key not in NORM_MIN:
            continue
        min_val = NORM_MIN[key]
        max_val = NORM_MAX[key]
        normalized[key] = max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
    return normalized


def kmeans(data: List[Dict], k: int, max_iter: int = 100) -> Tuple[List[Dict], List[int]]:
    if not data:
        return [], []

    n = len(data)
    if n <= k:
        return [data[i] for i in range(n)], list(range(n))

    # Initialize centroids randomly from the data
    centroids = random.sample(data, k)
    assignments = [0] * n

    for _ in range(max_iter):
        # Assignment step
        new_assignments = []
        for point in data:
            dists = [_euclidean_distance(point, c) for c in centroids]
            new_assignments.append(dists.index(min(dists)))

        if new_assignments == assignments:
            break
        assignments = new_assignments

        # Update step
        for c_idx in range(k):
            members = [data[i] for i in range(n) if assignments[i] == c_idx]
            if not members:
                continue

            new_centroid = {}
            for key in data[0].keys():
                vals = [m[key] for m in members if key in m]
                new_centroid[key] = sum(vals) / len(vals) if vals else 0.0
            centroids[c_idx] = new_centroid

    return centroids, assignments


def _label_cluster(centroid: Dict) -> str:
    """Assigns a meaningful name based on the dominant behavior."""
    # High Eff_abs + Low Vel_rev = Reactive/Efficient (The "Sniper" profile)
    # Low Eff_abs + High Pers_brk = Inertial/Trending (The "Bulldozer" profile)

    eff = centroid.get("eff_abs", 0.5)
    vel = centroid.get("vel_rev", 500.0)
    pers = centroid.get("pers_brk", 0.5)

    if eff > 0.5 and vel < 500:
        return "REACTIVE_EFFICIENT"
    elif pers > 0.5:
        return "INERTIAL_TRENDING"
    elif eff < 0.4:
        return "NOISY_UNCERTAIN"
    else:
        return "GENERAL_VOLATILE"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=3, help="Number of clusters")
    args = parser.parse_args()

    print(f"\n{'═'*65}\n  BUILDING BEHAVIORAL CLUSTERS (k={args.k})\n{'═'*65}")

    if not PROFILES_PATH.exists():
        print(f"❌ Behavioral profiles not found at {PROFILES_PATH}. Run behavioral_probe.py first.")
        return

    with open(PROFILES_PATH, "r") as f:
        profiles = json.load(f)

    if not profiles:
        print("❌ No profiles available to cluster.")
        return

    # Prepare data: only use the 3 DNA dimensions
    symbols = list(profiles.keys())
    dna_data = []
    for sym in symbols:
        p = profiles[sym]

        def _v(val, default=0.0):
            return val if val is not None else default

        dna_data.append(
            {
                "eff_abs": _v(p.get("eff_abs")),
                "vel_rev": _v(p.get("vel_rev")),
                "pers_brk": _v(p.get("pers_brk")),
            }
        )

    # Normalize
    normalized_dna = [_normalize(d) for d in dna_data]

    # Cluster
    centroids, assignments = kmeans(normalized_dna, args.k)

    # Build the final taxonomy
    clusters_fixed = {"clusters": {}}

    # To avoid duplicate names, we'll append a number if needed
    used_names = set()

    for c_idx in range(len(centroids)):
        members = [symbols[i] for i in range(len(symbols)) if assignments[i] == c_idx]
        if not members:
            continue

        # Denormalize centroid for reference
        centroid_dna = centroids[c_idx]
        denorm_centroid = {k: v * (NORM_MAX[k] - NORM_MIN[k]) + NORM_MIN[k] for k, v in centroid_dna.items()}

        base_name = _label_cluster(denorm_centroid)
        name = base_name
        counter = 1
        while name in used_names:
            name = f"{base_name}_{counter}"
            counter += 1
        used_names.add(name)

        clusters_fixed["clusters"][name] = {"centroid": denorm_centroid, "members": members, "n_members": len(members)}

    # Save to config/clusters_fixed.json
    with open(OUTPUT_PATH, "w") as f:
        json.dump(clusters_fixed, f, indent=2)

    print(f"\n✅ Behavioral clusters saved to {OUTPUT_PATH}")

    # Summary
    print("\n" + "=" * 60)
    print(f"{'Cluster Name':<25} {'Members':<20} {'DNA (Eff/Vel/Pers)':<20}")
    print("-" * 60)
    for name, data in clusters_fixed["clusters"].items():
        c = data["centroid"]
        dna_str = f"{c['eff_abs']:.2%}/{c['vel_rev']:.0f}s/{c['pers_brk']:.2%}"
        members_str = ", ".join(data["members"])
        print(f"{name:<25} {members_str:<20} {dna_str:<20}")
    print("=" * 60)


if __name__ == "__main__":
    main()
