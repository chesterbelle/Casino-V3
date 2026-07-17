"""
Profile Manager — Crystal Layer Parameter Management (Per-Symbol)

Loads and provides profile-specific parameters per symbol for the Crystal Layer.
Each coin MUST have an explicitly optimized profile in COIN_PROFILES.
No fallback to default profiles is allowed (Fail-Fast).
"""

import json
import logging
import os
from typing import Any, Dict

from config.coin_profiles import COIN_PROFILES

_logger = logging.getLogger("ProfileManager")
_opt_overrides = os.environ.get("OPT_PROFILE_OVERRIDES")
if _opt_overrides:
    try:
        parsed = json.loads(_opt_overrides)
        for profile_name, overrides in parsed.items():
            if profile_name in COIN_PROFILES:
                for key, value in overrides.items():
                    parts = key.split(".")
                    d = COIN_PROFILES[profile_name]
                    for part in parts[:-1]:
                        d = d.setdefault(part, {})
                    d[parts[-1]] = value
                _logger.info(f"📋 [PROFILE] Applied {len(overrides)} overrides to {profile_name}")
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        _logger.warning(f"⚠️ Failed to apply OPT_PROFILE_OVERRIDES: {e}")

logger = _logger


class ProfileManager:
    """
    Manages per-symbol profile parameters for the Crystal Layer.
    Enforces a strict 1:1 mapping between symbol and profile.
    """

    def __init__(self):
        self.profiles = COIN_PROFILES

    def get_profile(self, symbol: str) -> dict:
        """
        Get full profile dict for a symbol.
        Raises ValueError if the symbol does not have an explicitly optimized profile.
        """
        # Normalize symbol: 'AVAX/USDT:USDT' -> 'AVAXUSDT'
        lookup_symbol = symbol.replace("/", "").split(":")[0]

        if lookup_symbol not in self.profiles:
            error_msg = f"No optimized profile found for symbol '{symbol}' (lookup: '{lookup_symbol}'). Strict 1:1 mapping enforced."
            logger.critical(f"🚨 [PROFILE ERROR] {error_msg}")
            raise ValueError(error_msg)

        profile = self.profiles[lookup_symbol]

        # Check certification flag
        opt_status = profile.get("optimization_status", {})
        if not opt_status.get("is_certified", False):
            error_msg = (
                f"Profile for '{symbol}' is NOT certified (optimization_status.is_certified is False or missing)."
            )
            logger.critical(f"🚨 [PROFILE ERROR] {error_msg}")
            raise ValueError(error_msg)

        return profile

    def get_param(self, symbol: str, *path: str) -> Any:
        """
        Get a parameter from a symbol's profile by path.

        Args:
            symbol: Coin symbol
            *path: Path to the parameter (e.g., "targets", "tactical_absorption")

        Returns:
            The parameter value, or None if not found
        """
        profile = self.get_profile(symbol)

        value = profile
        for key in path:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def get_sensor_params(self, symbol: str, sensor_name: str) -> Dict:
        """Get all parameters for a specific sensor for a symbol."""
        return self.get_param(symbol, "sensors", sensor_name) or {}

    def get_scenario_params(self, symbol: str) -> Dict:
        """Get scenario configuration for a symbol."""
        return self.get_param(symbol, "scenarios") or {}

    def get_quality_scorer_params(self, symbol: str) -> Dict:
        """Get quality scorer parameters for a symbol."""
        return self.get_param(symbol, "quality_scorer") or {}

    def get_target_params(self, symbol: str, scenario: str, regime: str = None) -> Dict:
        """Get target parameters for a specific scenario and symbol."""
        targets = self.get_param(symbol, "targets", scenario) or {}
        if regime and "regime" in targets:
            regime_targets = targets["regime"]
            if regime in regime_targets:
                return regime_targets[regime]
        return targets

    def get_guardian_params(self, symbol: str) -> Dict:
        """Get guardian parameters for a symbol."""
        return self.get_param(symbol, "guardians") or {}

    def get_pressure_thresholds(self, symbol: str) -> Dict:
        """Get pressure engine thresholds for a symbol."""
        return self.get_param(symbol, "pressure_thresholds") or {}

    def get_risk_params(self, symbol: str) -> Dict:
        """Get risk parameters for a symbol."""
        return self.get_param(symbol, "risk") or {}

    def is_scenario_enabled(self, symbol: str, scenario: str) -> bool:
        """Check if a scenario is enabled in a symbol's profile."""
        enabled = self.get_param(symbol, "scenarios", "enabled") or []
        return scenario in enabled

    def get_all_profiles(self) -> Dict:
        """Get all available profiles."""
        return self.profiles


# Global instance
profile_manager = ProfileManager()
