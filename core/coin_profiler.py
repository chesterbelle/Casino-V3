"""
Coin Profiler — Dynamic Coin Classification

Classifies coins into tiers based on microstructure characteristics.
Uses profile thresholds from config/coin_profiles.py.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger("CoinProfiler")


class CoinProfiler:
    """
    Dynamic coin profiler that classifies coins into tiers
    based on their microstructure characteristics.
    """

    # Default profiles (can be overridden by config/coin_profiles.py)
    DEFAULT_PROFILES = {
        "TIER_1": {
            "trade_density": (0.02, 0.04),
            "volume_24h": (70_000_000, 200_000_000),
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "quality_bonus": 0.1,
        },
        "TIER_2": {
            "trade_density": (0.04, 0.08),
            "volume_24h": (200_000_000, 600_000_000),
            "tp_multiplier": 0.8,
            "sl_multiplier": 0.8,
            "quality_bonus": 0.0,
        },
        "TIER_3": {
            "trade_density": (0.08, 100),
            "volume_24h": (600_000_000, 1_000_000_000_000),
            "tp_multiplier": 0.5,
            "sl_multiplier": 0.5,
            "quality_penalty": -0.2,
        },
    }

    def __init__(self, profiles: Optional[Dict] = None):
        self.profiles = profiles or self.DEFAULT_PROFILES
        self.coin_cache: Dict[str, str] = {}

    def classify(self, symbol: str, coin_stats: Dict) -> str:
        """
        Classify a coin into a tier based on its microstructure stats.

        Args:
            symbol: Coin symbol (e.g., "BTC/USDT:USDT")
            coin_stats: Dict with keys like "trades_per_sec", "volume_24h_usd"

        Returns:
            Tier string: "TIER_1", "TIER_2", or "TIER_3"
        """
        # Check cache first
        if symbol in self.coin_cache:
            return self.coin_cache[symbol]

        density = coin_stats.get("trades_per_sec", 0)
        volume = coin_stats.get("volume_24h_usd", 0)

        # Score each tier
        best_tier = "TIER_3"  # Default to no edge
        best_score = -1

        for tier_name, tier_config in self.profiles.items():
            score = 0

            # Check trade density
            d_min, d_max = tier_config.get("trade_density", (0, 100))
            if d_min <= density <= d_max:
                score += 1

            # Check volume
            v_min, v_max = tier_config.get("volume_24h", (0, 1_000_000_000_000))
            if v_min <= volume <= v_max:
                score += 1

            if score > best_score:
                best_score = score
                best_tier = tier_name

        # Cache result
        self.coin_cache[symbol] = best_tier

        logger.info(f"🏷️ [PROFILE] {symbol} → {best_tier} (density={density:.3f}, volume={volume/1e6:.1f}M)")
        return best_tier

    def get_multipliers(self, tier: str) -> Dict:
        """Get TP/SL multipliers for a tier."""
        tier_config = self.profiles.get(tier, self.profiles.get("TIER_3"))
        return {
            "tp": tier_config.get("tp_multiplier", 1.0),
            "sl": tier_config.get("sl_multiplier", 1.0),
        }

    def get_quality_adjustment(self, tier: str) -> float:
        """Get quality score adjustment for a tier."""
        tier_config = self.profiles.get(tier, self.profiles.get("TIER_3"))
        return tier_config.get("quality_bonus", 0) + tier_config.get("quality_penalty", 0)


# Global instance
coin_profiler = CoinProfiler()
