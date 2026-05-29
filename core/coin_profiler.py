"""
Coin Profiler — Dynamic Coin Classification

Classifies coins into profiles based on microstructure characteristics.
Uses profile characteristics from config/coin_profiles.py.
"""

import logging
from typing import Dict

from config.coin_profiles import COIN_PROFILES, DEFAULT_PROFILE

logger = logging.getLogger("CoinProfiler")


class CoinProfiler:
    """
    Dynamic coin profiler that classifies coins into profiles
    based on their microstructure characteristics.
    """

    def __init__(self):
        self.profiles = COIN_PROFILES
        self.default_profile = DEFAULT_PROFILE
        self.coin_cache: Dict[str, str] = {}

    def classify(self, symbol: str, coin_stats: Dict) -> str:
        """
        Classify a coin into a profile based on its microstructure stats.

        Args:
            symbol: Coin symbol (e.g., "BTC/USDT:USDT")
            coin_stats: Dict with "trades_per_sec", "atr_pct", "volume_24h_usd"

        Returns:
            Profile name string
        """
        # Check cache first
        if symbol in self.coin_cache:
            return self.coin_cache[symbol]

        density = coin_stats.get("trades_per_sec", 0)
        atr = coin_stats.get("atr_pct", 0)
        volume = coin_stats.get("volume_24h_usd", 0)

        # Try each profile
        for profile_name, profile_config in self.profiles.items():
            if profile_name == DEFAULT_PROFILE:
                continue  # Skip default, use as fallback

            characteristics = profile_config.get("characteristics", {})
            match = True

            for feature, ranges in characteristics.items():
                if isinstance(ranges, dict):
                    min_val = ranges.get("min", 0)
                    max_val = ranges.get("max", float("inf"))

                    actual = 0
                    if feature == "atr_pct":
                        actual = atr
                    elif feature == "trades_per_sec":
                        actual = density
                    elif feature == "volume_24h_usd":
                        actual = volume

                    if not (min_val <= actual <= max_val):
                        match = False
                        break

            if match:
                self.coin_cache[symbol] = profile_name
                logger.info(f"🏷️ [PROFILE] {symbol} → {profile_name}")
                return profile_name

        # Default profile
        self.coin_cache[symbol] = self.default_profile
        logger.info(f"🏷️ [PROFILE] {symbol} → {self.default_profile} (default)")
        return self.default_profile


# Global instance
coin_profiler = CoinProfiler()
