"""
RegimeClassifier V1 - Multi-Layer AMT Regime Detection
Classifies market regime into TRENDING or RANGE based on 3 structural signals.
"""

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger("RegimeClassifier")


class RegimeClassifier:
    def __init__(self):
        # Tracking for VA Width Velocity
        self._last_va_width: Dict[str, float] = {}

    def classify(self, symbol: str, registry, params: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Classifies regime by taking a 3-signal vote.
        Returns: (regime_vote, debug_metadata)
        """
        votes = []
        metrics = {}

        # 1. POC Migration
        poc_migration = registry.get_poc_migration(symbol)
        poc_threshold = params.get("poc_migration_threshold", 0.003)
        if abs(poc_migration) > poc_threshold:
            votes.append("TRENDING")
        else:
            votes.append("RANGE")
        metrics["poc_migration"] = poc_migration

        # 2. Volatility Ratio (ATR_Short / ATR_Long)
        vol_ratio = registry.get_volatility_ratio(symbol)
        vol_threshold = params.get("vol_ratio_threshold", 1.3)
        if vol_ratio > vol_threshold:
            votes.append("TRENDING")
        else:
            votes.append("RANGE")
        metrics["vol_ratio"] = vol_ratio

        # 3. VA Width Velocity (or absolute expansion)
        va_expanding = self._is_va_expanding(symbol, registry, params, metrics)
        if va_expanding:
            votes.append("TRENDING")
        else:
            votes.append("RANGE")

        trend_votes = sum(1 for v in votes if v == "TRENDING")
        regime = "TRENDING" if trend_votes >= 2 else "RANGE"

        metrics["trend_votes"] = trend_votes
        metrics["regime"] = regime

        return regime, metrics

    def _is_va_expanding(self, symbol: str, registry, params: Dict[str, Any], metrics: Dict[str, Any]) -> bool:
        poc, vah, val = registry.get_structural(symbol)
        if not poc or not vah or not val or poc == 0:
            return False

        current_width_pct = (vah - val) / poc * 100
        metrics["va_width"] = current_width_pct

        last_width = self._last_va_width.get(symbol, current_width_pct)
        self._last_va_width[symbol] = current_width_pct

        expansion_threshold = params.get("va_expansion_threshold", 1.05)

        if last_width == 0:
            return False

        ratio = current_width_pct / last_width
        metrics["va_expansion_ratio"] = ratio

        abs_width_threshold = params.get("va_abs_width_threshold", 1.5)
        if current_width_pct > abs_width_threshold:
            return True

        return ratio >= expansion_threshold


# Global singleton
regime_classifier = RegimeClassifier()
