import sys

sys.path.insert(0, ".")

import json
import math
from typing import Dict, List

import numpy as np

# Reutilizamos kmeans y compute_silhouette de cluster_builder
from utils.cluster_builder import (
    NORM_MAX,
    NORM_MIN,
    _normalize,
    compute_silhouette,
    kmeans,
)


def build_fixed_clusters(k=5):
    with open("config/firmas.json", "r") as f:
        firmas = json.load(f)

    symbols = list(firmas.keys())
    data = [firmas[s] for s in symbols]
    normalized = [_normalize(d, NORM_MIN, NORM_MAX) for d in data]

    # K-Means determinista (semilla 42)
    centroids, assignments = kmeans(normalized, k, seed=42)

    cluster_names = ["MEGA_LIQUID", "MAJOR_LIQUID", "MID_LIQUID", "THIN_VOLATILE", "ILLIQUID_SPEC"]
    clusters = {}

    for c_idx in range(k):
        members = [symbols[i] for i in range(len(symbols)) if assignments[i] == c_idx]
        denorm_centroid = {}
        for dim in ["tick_size_efficiency", "book_density", "volume_vol_ratio", "speed"]:
            min_v = NORM_MIN.get(dim, 0)
            max_v = NORM_MAX.get(dim, 1)
            denorm_centroid[dim] = centroids[c_idx].get(dim, 0.5) * (max_v - min_v) + min_v

        clusters[cluster_names[c_idx]] = {
            "centroid": denorm_centroid,
            "members": members,
            "n_members": len(members),
        }

    config = {"version": "4.0_FIXED", "clusters": clusters}

    with open("config/clusters_fixed.json", "w") as f:
        json.dump(config, f, indent=2)
    print("✅ clusters_fixed.json generado.")


if __name__ == "__main__":
    build_fixed_clusters()
