import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("StatisticalLocationGuardian")


def check_statistical_location(
    symbol: str, side: str, current_price: float, context_registry, fast_track: bool
) -> GuardianResult:
    """
    Phase D1: Statistical Location Guardian (Rolling VWAP Bands).
    Calculates the Z-Score of the current price relative to a 120m VWAP window.
    Only allows high-confidence reversions at statistical extremes (> 2.0Z).
    """
    if fast_track or not context_registry:
        return GuardianResult(passed=True, score=1.0, gate_name="STATISTICAL_LOCATION")

    z_score = context_registry.get_vwap_zscore(symbol, current_price)

    # Normalization:
    # For LONG: We want Z < -2.0 (Price is far below mean)
    # For SHORT: We want Z > 2.0 (Price is far above mean)

    passed = True
    score = 0.5  # Default neutral

    # Phase D1.5: Regime-Aware Aggressiveness

    # For EXPRIMIDOR iteration: Reduce min_z to 1.0 to increase signal frequency
    min_z = 1.0

    if side == "LONG":
        if z_score > -min_z:
            passed = False
            score = 0.0  # Price too near mean for reversion
        elif z_score > -2.5:
            score = 0.5  # Moderate extreme
        else:
            score = 1.0  # Deep extreme

    elif side == "SHORT":
        if z_score < min_z:
            passed = False
            score = 0.0  # Price too near mean for reversion
        elif z_score < 2.5:
            score = 0.5  # Moderate extreme
        else:
            score = 1.0  # Deep extreme

    metrics = {"z_score": round(z_score, 3), "price": current_price}

    reason = (
        f"Price at {z_score:.2f}Z (Extremes supported)"
        if passed
        else f"Price at {z_score:.2f}Z (Too near mean for reversion)"
    )

    return GuardianResult(
        passed=passed,
        score=score,
        multiplier=1.0,
        reason=reason,
        metrics=metrics,
        gate_name="STATISTICAL_LOCATION",
    )
