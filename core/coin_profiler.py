"""
Coin Profiler — Dynamic Coin Classification

Classifies coins into profiles based on microstructure characteristics.
Uses profile characteristics from config/coin_profiles.py.

Classification Metrics (measured from L2 data):
- spread_ratio: current_spread / avg_5m_spread (1.0 = normal, >1.0 = wide)
- depth_ratio: L2 bid_vol / ask_vol within 0.2% of mid (higher = deeper book)
- speed: trades per second (higher = more active market)
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
            coin_stats: Dict with "spread_ratio", "depth_ratio", "speed"

        Returns:
            Profile name string
        """
        # Check cache first
        if symbol in self.coin_cache:
            return self.coin_cache[symbol]

        spread_ratio = coin_stats.get("spread_ratio", 1.0)
        depth_ratio = coin_stats.get("depth_ratio", 1.0)
        speed = coin_stats.get("speed", 0.0)

        # Try each profile
        for profile_name, profile_config in self.profiles.items():
            characteristics = profile_config.get("characteristics", {})
            match = True

            for feature, ranges in characteristics.items():
                if isinstance(ranges, dict):
                    min_val = ranges.get("min", 0)
                    max_val = ranges.get("max", float("inf"))

                    actual = 0
                    if feature == "spread_ratio":
                        actual = spread_ratio
                    elif feature == "depth_ratio":
                        actual = depth_ratio
                    elif feature == "speed":
                        actual = speed

                    if not (min_val <= actual <= max_val):
                        match = False
                        break

            if match:
                self.coin_cache[symbol] = profile_name
                logger.info(f"🏷️ [PROFILE] {symbol} → {profile_name}")
                return profile_name

        # Default profile — NO MATCH means wrong params, verify before trading
        self.coin_cache[symbol] = self.default_profile
        logger.critical(
            f"🚨 [UNKNOWN COIN] {symbol} — no match to any profile. "
            f"Using DEFAULT ({self.default_profile}). "
            f"Verify params before trading!"
        )
        return self.default_profile


# Global instance
coin_profiler = CoinProfiler()
