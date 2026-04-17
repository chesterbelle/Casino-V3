"""
Strategy Configuration - Phase 600 Pivot
Decouples strategy-specific logic from global trading configuration.
"""

# LTA V4: Structural Reversion Settings
LTA_PROXIMITY_THRESHOLD = 0.0025  # 0.25% distance from VA edges (VAH/VAL)
LTA_SL_TICK_BUFFER = 3.0  # Phase 2000: 3 ticks beyond edge (0.15% buffer — crypto spread room)
LTA_TICK_PROXY = 0.0005  # 0.05% as a proxy for a single price tick

# Order Flow Guardians (AMT/Axia Thresholds)
LTA_POC_MIGRATION_THRESHOLD = 0.0050  # 0.5% max migration in opposite direction (Battle-Ready)
LTA_VA_INTEGRITY_MIN = 0.08  # Min Integrity Score — global fallback (Refined Battle-Ready)
LTA_FAILED_AUCTION_BODY_MIN = 0.05  # Rejection wick must be 5% of body (Battle-Ready)
LTA_FAILED_AUCTION_LOOKBACK = 3  # Phase 2000: Check last N candles for probe (Axia-style)
LTA_CVD_NEUTRAL_THRESHOLD = 0.0  # CVD neutrality for divergence check

# Phase B1: Dynamic VA Integrity thresholds by liquidity window
# Crypto profiles are inherently thinner during low-liquidity windows (Asian, Quiet)
# and tighter during peak hours (Overlap). This adapts the threshold accordingly.
LTA_VA_INTEGRITY_BY_WINDOW = {
    "asian": 0.06,
    "london": 0.10,
    "overlap": 0.12,
    "ny": 0.10,
    "quiet": 0.05,
}

# Registry of active playbooks for SetupEngine
ACTIVE_STRATEGIES = ["LTA_STRUCTURAL", "LTA_CASCADE"]


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
        "LiquidationCascade": "Tactical",
        "Heartbeat": "Health",
    }
    # Check for prefix matches to be robust against naming variations
    for key, value in types.items():
        if key in sensor_name:
            return value
    return "Tactical"
