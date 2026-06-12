"""
Coin Profiler — Centroid-Based Microstructure Classification (Institutional)

Classifies coins into clusters based on Euclidean distance to learned
centroids. Uses 4 institutional microstructure dimensions:

  - tick_size_efficiency: how fast spread clears (0-1)
  - book_density: total volume / spread (depth relative to cost)
  - volume_vol_ratio: energy to move price (USD volume / volatility)
  - speed: trades per second

Architecture:
  Capa 1: clusters.json contains centroids learned offline
  Capa 2: This module computes metrics and finds nearest cluster
  Capa 3: profile_manager.py applies parameters for that cluster
"""

import json
import logging
import math
from pathlib import Path
from typing import Dict, Optional

from config.coin_profiles import DEFAULT_PROFILE

logger = logging.getLogger("CoinProfiler")

CLUSTERS_PATH = Path("config/clusters_fixed.json")


def _load_clusters() -> dict:
    if not CLUSTERS_PATH.exists():
        logger.critical(f"🚨 Clusters file not found: {CLUSTERS_PATH}")
        return {}
    with open(CLUSTERS_PATH) as f:
        return json.load(f)


def _euclidean_distance(a: dict, b: dict) -> float:
    keys = set(a.keys()) & set(b.keys())
    if not keys:
        return float("inf")
    return math.sqrt(sum((a.get(k, 0) - b.get(k, 0)) ** 2 for k in keys))


def _normalize(metrics: dict, norm_min: dict, norm_max: dict, skip_log1p: bool = False) -> dict:
    normalized = {}
    for key, value in metrics.items():
        if value is None:
            normalized[key] = 0.5
            continue
        # Apply log1p scaling for huge-range dimensions (skip if already log1p'd)
        if not skip_log1p and key in ("book_density", "volume_vol_ratio") and value > 0:
            value = math.log1p(value)
        min_val = norm_min.get(key, 0)
        max_val = norm_max.get(key, 1)
        if max_val <= min_val:
            normalized[key] = 0.5
            continue
        normalized[key] = max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
    return normalized


class CoinProfiler:
    """
    Centroid-based coin profiler. Classifies coins by Euclidean distance
    to cluster centroids in normalized microstructure space.
    """

    def __init__(self):
        self.config = _load_clusters()
        self.clusters = self.config.get("clusters", {})
        self.dimensions = self.config.get("dimensions", [])
        self.norm_min = self.config.get("normalization", {}).get("min", {})
        self.norm_max = self.config.get("normalization", {}).get("max", {})
        # Fallback to cluster_builder defaults if normalization missing from config
        if not self.norm_min or not self.norm_max:
            from utils.cluster_constants import STATIC_NORM_MAX, STATIC_NORM_MIN

            if not self.norm_min:
                self.norm_min = STATIC_NORM_MIN
            if not self.norm_max:
                self.norm_max = STATIC_NORM_MAX
        self.threshold = self.config.get("threshold", {}).get("max_distance", 0.35)
        self.coin_cache: Dict[str, str] = {}

    def classify(self, symbol: str, metrics: Dict) -> str:
        """
        Classify a coin into a cluster based on microstructure metrics.

        Args:
            symbol: Coin symbol (e.g., "BTC/USDT:USDT")
            metrics: Dict with 4 institutional dimensions

        Returns:
            Cluster name (profile name)
        """
        if symbol in self.coin_cache:
            return self.coin_cache[symbol]

        if not self.clusters:
            logger.critical("🚨 No clusters loaded — using DEFAULT_PROFILE")
            return DEFAULT_PROFILE

        # Alias mapping: support old metric names
        aliased = dict(metrics)
        if "spread_ratio" in metrics and "book_density" not in metrics:
            aliased["book_density"] = metrics["spread_ratio"]

        # Normalize metrics
        normalized = _normalize(aliased, self.norm_min, self.norm_max)

        # Compute distance to each centroid
        # Centroids are stored in log1p space (de-normalized from [0,1]).
        # Normalize with skip_log1p=True since they're already log1p'd.
        distances = {}
        for cluster_name, cluster_data in self.clusters.items():
            centroid = cluster_data.get("centroid", {})
            if not centroid:
                continue
            centroid_norm = {
                k: v
                for k, v in _normalize(centroid, self.norm_min, self.norm_max, skip_log1p=True).items()
                if k in normalized
            }
            norm_filtered = {k: v for k, v in normalized.items() if k in centroid_norm}
            dist = _euclidean_distance(norm_filtered, centroid_norm)
            distances[cluster_name] = dist

        if not distances:
            logger.critical(f"🚨 [UNKNOWN COIN] {symbol} — no clusters to compare. Using DEFAULT.")
            return DEFAULT_PROFILE

        closest = min(distances, key=distances.get)
        min_dist = distances[closest]

        if min_dist <= self.threshold:
            self.coin_cache[symbol] = closest
            logger.info(f"🏷️ [PROFILE] {symbol} → {closest} (distance: {min_dist:.3f})")
            return closest

        sorted_d = sorted(distances.items(), key=lambda x: x[1])
        candidates = ", ".join(f"{n}({d:.3f})" for n, d in sorted_d[:3])
        logger.warning(
            f"⚠️ [UNKNOWN COIN] {symbol} — min distance {min_dist:.3f} > threshold {self.threshold}. "
            f"Candidates: {candidates}. Using DEFAULT ({DEFAULT_PROFILE})."
        )
        self.coin_cache[symbol] = DEFAULT_PROFILE
        return DEFAULT_PROFILE

    def get_distances(self, metrics: Dict) -> Dict[str, float]:
        """Get distances to all clusters (for diagnostic purposes)."""
        if not self.clusters:
            return {}

        aliased = dict(metrics)
        if "spread_ratio" in metrics and "book_density" not in metrics:
            aliased["book_density"] = metrics["spread_ratio"]

        normalized = _normalize(aliased, self.norm_min, self.norm_max)

        # Centroids are stored in log1p space (de-normalized from [0,1]).
        # Normalize with skip_log1p=True since they're already log1p'd.
        distances = {}
        for cluster_name, cluster_data in self.clusters.items():
            centroid = cluster_data.get("centroid", {})
            if not centroid:
                continue
            centroid_norm = {
                k: v
                for k, v in _normalize(centroid, self.norm_min, self.norm_max, skip_log1p=True).items()
                if k in normalized
            }
            norm_filtered = {k: v for k, v in normalized.items() if k in centroid_norm}
            distances[cluster_name] = _euclidean_distance(norm_filtered, centroid_norm)

        return dict(sorted(distances.items(), key=lambda x: x[1]))

    def invalidate_cache(self, symbol: Optional[str] = None):
        if symbol:
            self.coin_cache.pop(symbol, None)
        else:
            self.coin_cache.clear()


coin_profiler = CoinProfiler()
