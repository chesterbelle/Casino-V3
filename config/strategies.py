"""
Strategy Configuration - Phase 600 Pivot
Decouples strategy-specific logic from global trading configuration.
"""

# LTA V4: Structural Reversion Settings
LTA_PROXIMITY_THRESHOLD = 0.0035  # Phase 2500: Relaxed to 0.35% for Volume Expansion
LTA_SL_TICK_BUFFER = 6.0  # Phase 1200: 6 ticks (0.30% buffer — edge-audit aligned 0.3/0.3)
LTA_TICK_PROXY = 0.0005  # 0.05% as a proxy for a single price tick

# Order Flow Guardians (LTA V5 Certified Thresholds)
LTA_POC_MIGRATION_THRESHOLD = 0.0050  # 0.5% max migration (Reverted from 0.8% for Alpha)
LTA_VA_INTEGRITY_MIN = 0.01  # Phase 2500: Relaxed to 0.01 for Volume Expansion
LTA_FAILED_AUCTION_BODY_MIN = 0.05  # Kept for reference but no longer used in Phase 2200
LTA_FAILED_AUCTION_LOOKBACK = 10  # Phase 2200: Extended from 3 to 10 candles
LTA_CVD_NEUTRAL_THRESHOLD = 0.0  # CVD neutrality for divergence check

# Sizing Multipliers for Soft Gates (Phase 2350)
LTA_SOFT_GATE_REDUCTION = 0.5  # 50% sizing reduction for borderline conditions
LTA_TRANSITION_Z_THRESHOLD = 2.5  # Z-score requirement to trade in TRANSITION state (Reverted from 2.2)

# Phase 2400: Relaxed VA Integrity thresholds (Deep Analysis - 89.7% rejection rate was too high)
LTA_VA_INTEGRITY_BY_WINDOW = {
    "asian": 0.01,
    "london": 0.01,
    "overlap": 0.02,
    "ny": 0.01,
    "quiet": 0.01,
}

# Registry of active playbooks for SetupEngine
ACTIVE_STRATEGIES = ["AbsorptionScalpingV2"]


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
