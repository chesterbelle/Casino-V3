"""
Profile Manager — Crystal Layer Parameter Management

Loads and provides profile-specific parameters for the entire Crystal Layer.
Each coin is assigned a profile, and all components use the profile's parameters.
"""

import logging
from typing import Any, Dict

from config.coin_profiles import COIN_PROFILES, DEFAULT_PROFILE

logger = logging.getLogger("ProfileManager")


class ProfileManager:
    """
    Manages profile-specific parameters for the Crystal Layer.
    Each coin is classified into a profile, and all components
    use the profile's parameters.
    """

    def __init__(self):
        self.profiles = COIN_PROFILES
        self.default_profile = DEFAULT_PROFILE
        self.current_profile_name = None
        self.current_profile = None

    def set_profile(self, profile_name: str) -> bool:
        """
        Load a profile by name and apply its parameters to config modules.

        Args:
            profile_name: Name of the profile to load

        Returns:
            True if profile was loaded, False if not found
        """
        if profile_name in self.profiles:
            self.current_profile_name = profile_name
            self.current_profile = self.profiles[profile_name]
            self._apply_to_config()
            logger.info(f"📋 [PROFILE] Loaded: {profile_name} — {self.current_profile.get('description', '')}")
            return True
        else:
            logger.warning(f"⚠️ [PROFILE] Unknown profile: {profile_name}, using default")
            self.current_profile_name = self.default_profile
            self.current_profile = self.profiles[self.default_profile]
            self._apply_to_config()
            return False

    def _apply_to_config(self):
        """Apply current profile parameters to config modules."""
        if not self.current_profile:
            return

        # Apply absorption sensor parameters
        sensor_params = self.current_profile.get("sensors", {}).get("absorption_detector", {})
        if sensor_params:
            try:
                import config.absorption as abs_config

                if "z_score_min" in sensor_params:
                    abs_config.ABSORPTION_MIN_Z_SCORE = sensor_params["z_score_min"]
                if "concentration_min" in sensor_params:
                    abs_config.ABSORPTION_MIN_CONCENTRATION = sensor_params["concentration_min"]
                if "noise_max" in sensor_params:
                    abs_config.ABSORPTION_MAX_NOISE = sensor_params["noise_max"]
                logger.info(
                    f"📋 [PROFILE] Applied absorption params: Z={sensor_params.get('z_score_min')}, Conc={sensor_params.get('concentration_min')}, Noise={sensor_params.get('noise_max')}"
                )
            except Exception as e:
                logger.error(f"❌ [PROFILE] Failed to apply absorption params: {e}")

    def get_param(self, *path: str) -> Any:
        """
        Get a parameter from the current profile by path.

        Args:
            *path: Path to the parameter (e.g., "sensors", "absorption_detector", "z_score_min")

        Returns:
            The parameter value, or None if not found
        """
        if not self.current_profile:
            return None

        value = self.current_profile
        for key in path:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def get_sensor_params(self, sensor_name: str) -> Dict:
        """Get all parameters for a specific sensor."""
        return self.get_param("sensors", sensor_name) or {}

    def get_scenario_params(self) -> Dict:
        """Get scenario configuration."""
        return self.get_param("scenarios") or {}

    def get_quality_scorer_params(self) -> Dict:
        """Get quality scorer parameters."""
        return self.get_param("quality_scorer") or {}

    def get_target_params(self, scenario: str) -> Dict:
        """Get target parameters for a specific scenario."""
        return self.get_param("targets", scenario) or {}

    def get_guardian_params(self) -> Dict:
        """Get guardian parameters."""
        return self.get_param("guardians") or {}

    def get_risk_params(self) -> Dict:
        """Get risk parameters."""
        return self.get_param("risk") or {}

    def is_scenario_enabled(self, scenario: str) -> bool:
        """Check if a scenario is enabled in the current profile."""
        enabled = self.get_param("scenarios", "enabled") or []
        return scenario in enabled

    def get_all_profiles(self) -> Dict:
        """Get all available profiles."""
        return self.profiles


# Global instance
profile_manager = ProfileManager()
