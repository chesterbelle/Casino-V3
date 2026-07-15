"""
Validation schemas for AMT detector parameters.

Provides Pydantic models for validating profile parameters
to prevent invalid configurations (negative cooldowns, etc.)
"""

import logging

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class AbsorptionParams(BaseModel):
    """Validation schema for AbsorptionDetector parameters."""

    cooldown: float = Field(180.0, ge=0, description="Cooldown between signals in seconds")
    level_tolerance_pct: float = Field(0.003, gt=0, description="Proximity tolerance to structural levels")
    z_score_min: float = Field(2.0, ge=0, description="Minimum CVD velocity z-score")
    volatility_z_max: float = Field(2.5, gt=0, description="Maximum volatility z-score allowed")
    displacement_z_max: float = Field(3.0, gt=0, description="Maximum price displacement z-score")
    absorption_score_min: float = Field(0.5, ge=0, le=1.0, description="Minimum absorption score v2 (0-1)")


class FailedBreakoutParams(BaseModel):
    """Validation schema for FailedBreakoutDetector parameters."""

    cooldown: float = Field(60.0, ge=0, description="Cooldown between signals in seconds")
    max_break_age: float = Field(60.0, gt=0, description="Maximum age of a breakout before it expires")
    min_break_distance_pct: float = Field(0.0003, gt=0, description="Minimum distance from level to count as breakout")
    exhaustion_z: float = Field(
        2.0, gt=0, description="Z-score threshold for exhaustion gate (CVD too strong in break direction)"
    )
    divergence_z: float = Field(
        0.5, gt=0, description="Z-score threshold for divergence detection (CVD too weak relative to break)"
    )


class LiquidityExhaustionParams(BaseModel):
    """Validation schema for LiquidityExhaustionDetector parameters."""

    cooldown: float = Field(30.0, ge=0, description="Cooldown between signals in seconds")
    level_tolerance_pct: float = Field(0.0005, gt=0, description="Price tolerance for level test matching")
    test_memory_seconds: float = Field(120.0, gt=0, description="How long to remember level tests")
    min_tests: int = Field(3, ge=2, le=50, description="Minimum number of tests to trigger signal")
    declining_threshold: float = Field(0.7, gt=0, le=1.0, description="Threshold for declining delta detection")
    min_bounce_pct: float = Field(0.0003, ge=0, description="Minimum bounce percentage from level")


class TrendAcceptanceParams(BaseModel):
    """Validation schema for TrendAcceptanceDetector parameters."""

    cooldown: float = Field(600.0, ge=0, description="Cooldown between signals in seconds")
    cvd_confirmation_threshold: float = Field(5.0, gt=0, description="CVD slope threshold for breakout confirmation")
    pullback_bps: float = Field(12.0, gt=0, description="Pullback distance in basis points")
    min_breakout_distance_bps: float = Field(20.0, gt=0, description="Minimum breakout distance in bps")


VALIDATION_MAP = {
    "absorption": AbsorptionParams,
    "failed_breakout": FailedBreakoutParams,
    "liquidity_exhaustion": LiquidityExhaustionParams,
    "trend_acceptance": TrendAcceptanceParams,
}


def validate_params(params_dict: dict, scenario: str) -> dict:
    """
    Validate and normalize detector parameters.

    Args:
        params_dict: Raw parameter dictionary from profile
        scenario: One of the 4 AMT scenario names

    Returns:
        Validated parameter dictionary with defaults applied
    """
    if scenario not in VALIDATION_MAP:
        logger.warning("Unknown scenario '%s' for validation", scenario)
        return params_dict

    try:
        schema = VALIDATION_MAP[scenario]
        validated = schema(**params_dict)
        # Preserve extra profile keys (e.g. regime_*, pullback_tolerance_pct,
        # max_pullback_penetration_pct, min_candles_outside) that the Pydantic
        # schema does not model but the sensor still consumes via bridges.
        return {**validated.model_dump(), **params_dict}
    except ValidationError as e:
        logger.error("Parameter validation error for %s: %s", scenario, e)
        # Return partial params with defaults for invalid fields
        cleaned = dict(params_dict)
        for error in e.errors():
            field = error["loc"][0]
            logger.warning("Invalid param '%s' for %s: %s", field, scenario, error["msg"])
            # Skip invalid field, let it fall back to default
            cleaned.pop(field, None)
        validated = schema(**cleaned)
        return {**validated.model_dump(), **cleaned}
    except Exception as e:
        logger.exception("Unexpected validation error for %s: %s", scenario, e)
        return params_dict
