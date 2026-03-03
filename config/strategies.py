"""
====================================================
🎯 SENSOR TYPES & TRADING STRATEGIES — CASINO V3
====================================================

ARCHITECTURE:
- SENSOR_TYPES: Categorize sensors by WHAT they detect
- STRATEGIES: Define HOW to trade, using sensors from any type

A sensor belongs to ONE type but can be used in MULTIPLE strategies.
"""

from typing import Dict, List, Set

# =====================================================
# 📊 SENSOR TYPES (What the sensor detects)
# =====================================================

SENSOR_TYPES: Dict[str, List[str]] = {
    # -----------------------------------------------------
    # VOLUME ANALYSIS - Volume-based signals (Dale)
    # -----------------------------------------------------
    "VolumeAnalysis": [
        "VolumeImbalance",
        "VolumeSpike",
        "VSAReversal",
        "AbsorptionBlock",
    ],
    # -----------------------------------------------------
    # STRUCTURAL CONTEXT - Market Profile (Dalton)
    # -----------------------------------------------------
    "RegimeFilter": [
        "OneTimeframing",
        "SessionValueArea",
    ],
    # -----------------------------------------------------
    # ORDER FLOW - Footprint & Delta analysis (Dale/Dalton)
    # -----------------------------------------------------
    "OrderFlow": [
        "FootprintImbalance",
        "FootprintAbsorption",
        "FootprintPOCRejection",
        "FootprintDeltaDivergence",
        "FootprintStackedImbalance",
        "FootprintTrappedTraders",
        "FootprintVolumeExhaustion",
        "FootprintDeltaPoCShift",
        "CumulativeDelta",
    ],
}


# =====================================================
# 🎯 TRADING STRATEGIES (How to trade)
# =====================================================

STRATEGIES: Dict[str, dict] = {
    # -----------------------------------------------------
    # FOOTPRINT SCALPER - Order Flow (Pure Baseline)
    # -----------------------------------------------------
    "FootprintScalper": {
        "enabled": True,
        "description": "Scalping based on Footprint Imbalance and Market Profile structural context.",
        "logic": "Follow aggressive imbalances, fade absorption. Context via Dalton One-Timeframing.",
        "sensors": [
            # --- Primary Triggers (Order Flow - Dale) ---
            "FootprintAbsorption",
            "FootprintDeltaDivergence",
            "FootprintVolumeExhaustion",
            "FootprintPOCRejection",
            "FootprintTrappedTraders",
            "FootprintImbalance",
            "FootprintStackedImbalance",
            "FootprintDeltaPoCShift",
            "CumulativeDelta",
            "OneTimeframing",
            "SessionValueArea",
            # --- High Performance Confirmations ---
            "VolumeSpike",
        ],
        "max_positions": 1,
    },
}


# =====================================================
# 🔧 HELPER FUNCTIONS
# =====================================================


def get_sensor_type(sensor_name: str) -> str:
    """Get the type category for a sensor."""
    for type_name, sensors in SENSOR_TYPES.items():
        if sensor_name in sensors:
            return type_name
    return "Unknown"


def get_sensors_by_type(type_name: str) -> List[str]:
    """Get all sensors of a specific type."""
    return SENSOR_TYPES.get(type_name, [])


def get_active_sensors() -> Set[str]:
    """Get sensors from all enabled strategies."""
    active = set()
    for config in STRATEGIES.values():
        if config.get("enabled", False):
            active.update(config.get("sensors", []))
    return active


def get_enabled_strategies() -> List[str]:
    """Get list of enabled strategy names."""
    return [name for name, config in STRATEGIES.items() if config.get("enabled", False)]


def get_strategy_for_sensor(sensor_name: str) -> List[str]:
    """Find which strategies use a sensor (can be multiple)."""
    strategies = []
    for name, config in STRATEGIES.items():
        if sensor_name in config.get("sensors", []):
            strategies.append(name)
    return strategies


def get_strategy_config(strategy_name: str) -> dict:
    """Get configuration for a specific strategy."""
    return STRATEGIES.get(strategy_name, {})


def enable_only(strategy_name: str):
    """Enable only the specified strategy, disable others."""
    for name, config in STRATEGIES.items():
        config["enabled"] = name == strategy_name


def enable_strategies(strategy_names: List[str]):
    """Enable multiple strategies."""
    for name, config in STRATEGIES.items():
        config["enabled"] = name in strategy_names
