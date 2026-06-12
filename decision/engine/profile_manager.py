"""
Profile Manager — Crystal Layer Parameter Management (Per-Symbol)

Loads and provides profile-specific parameters per symbol for the Crystal Layer.
Each coin is assigned a profile, and all components use that symbol's profile parameters.
"""

import logging
import os
from typing import Any, Dict

from config.coin_profiles import COIN_PROFILES, DEFAULT_PROFILE

logger = logging.getLogger("ProfileManager")


class ProfileManager:
    """
    Manages per-symbol profile parameters for the Crystal Layer.
    Each symbol is classified into a profile, and all components
    read parameters for the specific symbol being processed.
    """

    def __init__(self):
        self.profiles = COIN_PROFILES
        self.default_profile = DEFAULT_PROFILE
        self.symbol_profiles: Dict[str, str] = {}  # symbol → profile_name

    def set_profile(self, symbol: str, profile_name: str) -> bool:
        """
        Set profile for a specific symbol.
        If CASINO_FORCE_PROFILE env var is set, overrides the profile.

        Args:
            symbol: Coin symbol (e.g., "BTC/USDT:USDT")
            profile_name: Name of the profile to assign

        Returns:
            True if profile was set, False if not found (uses default)
        """
        # Allow forcing a specific profile via environment variable
        forced = os.environ.get("CASINO_FORCE_PROFILE")
        if forced:
            profile_name = forced

        if profile_name in self.profiles:
            self.symbol_profiles[symbol] = profile_name
            logger.info(f"📋 [PROFILE] {symbol} → {profile_name}")
            return True
        else:
            logger.warning(f"⚠️ [PROFILE] Unknown profile: {profile_name}, using default for {symbol}")
            self.symbol_profiles[symbol] = self.default_profile
            return False

    def get_profile_name(self, symbol: str) -> str:
        """Get profile name for a symbol. If not set, resolves from fixed taxonomy."""
        if symbol in self.symbol_profiles:
            return self.symbol_profiles[symbol]

        # Attempt to resolve from fixed taxonomy
        try:
            import json

            with open("config/clusters_fixed.json") as f:
                data = json.load(f)

            for profile, info in data["clusters"].items():
                if symbol in info.get("members", []):
                    return profile
        except Exception as e:
            logger.debug(f"Taxonomy lookup failed for {symbol}: {e}")

        return self.default_profile

    def get_profile(self, symbol: str) -> dict:
        """Get full profile dict for a symbol."""
        name = self.get_profile_name(symbol)
        return self.profiles.get(name, {})

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
        """Get target parameters for a specific scenario and symbol.

        If regime is provided and per-regime targets exist, returns regime-specific
        targets. Falls back to generic targets if no per-regime override.
        """
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
