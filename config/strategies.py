"""
Strategy Configuration - Phase 600 Pivot
Decouples strategy-specific logic from global trading configuration.
"""

# LTA V4: Structural Reversion Settings
LTA_PROXIMITY_THRESHOLD = 0.0025  # 0.25% distance from VA edges (VAH/VAL)
LTA_SL_TICK_BUFFER = 2.0  # Number of ticks beyond the edge for SL (proxy: 0.05% per tick)
LTA_TICK_PROXY = 0.0005  # 0.05% as a proxy for a single price tick

# Order Flow Guardians (AMT/Axia Thresholds)
LTA_POC_MIGRATION_THRESHOLD = 0.0050  # 0.5% max migration in opposite direction (Battle-Ready)
LTA_VA_INTEGRITY_MIN = 0.08  # Min Integrity Score for magnetic POC (Refined Battle-Ready)
LTA_FAILED_AUCTION_BODY_MIN = 0.05  # Rejection wick must be 5% of body (Battle-Ready)
LTA_CVD_NEUTRAL_THRESHOLD = 0.0  # CVD neutrality for divergence check

# Registry of active playbooks for SetupEngine
ACTIVE_STRATEGIES = ["LTA_STRUCTURAL"]


def get_sensor_type(sensor_name: str) -> str:
    """Categorizes sensors for cooldown and logic handling."""
    types = {
        "OneTimeframing": "RegimeFilter",
        "SessionValueArea": "Context",
        "VolatilitySpike": "Tactical",
        "FootprintImbalance": "Tactical",
        "FootprintAbsorption": "Tactical",
        "FootprintPOCRejection": "Tactical",
        "FootprintDeltaDivergence": "Tactical",
        "FootprintStackedImbalance": "Tactical",
        "FootprintTrappedTraders": "Tactical",
        "FootprintVolumeExhaustion": "Tactical",
        "FootprintDeltaPoCShift": "Tactical",
        "CumulativeDelta": "Tactical",
        "BigOrder": "Tactical",
        "DeltaVelocity": "Tactical",
        "Heartbeat": "Health",
    }
    # Check for prefix matches to be robust against naming variations
    for key, value in types.items():
        if key in sensor_name:
            return value
    return "Tactical"
