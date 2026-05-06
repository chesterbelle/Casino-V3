import logging

from .guardian_result import GuardianResult, SetupMode

logger = logging.getLogger("StatisticalLocationGuardian")


def check_statistical_location(
    symbol: str, side: str, current_price: float, context_registry, fast_track: bool
) -> GuardianResult:
    """
    Phase D1: Statistical Location Guardian (Rolling VWAP Bands).
    V3 Update: Supports both Reversion and Continuation setups.
    """
    if fast_track or not context_registry:
        return GuardianResult(passed=True, score=1.0, gate_name="STATISTICAL_LOCATION")

    z_score = context_registry.get_vwap_zscore(symbol, current_price)

    # Phase D1.5: Sniper Mode (Dynamic Threshold)
    min_z = 2.0
    setup_mode = SetupMode.REVERSION

    # Get regime context to check alignment
    regime_data = getattr(context_registry, "_regime_v2", {}).get(symbol, {})
    regime = regime_data.get("regime", "BALANCE")
    direction = regime_data.get("direction", "NEUTRAL")
    confidence = regime_data.get("confidence", 0.0)

    # V3 Logic: Determine if we are in Continuation or Reversion
    if regime != "BALANCE" and confidence > 0.15:
        if (direction == "UP" and side == "LONG") or (direction == "DOWN" and side == "SHORT"):
            setup_mode = SetupMode.CONTINUATION
            min_z = 1.0  # Lower threshold for trend-aligned "pullback" entries

    passed = True
    score = 0.5

    if setup_mode == SetupMode.CONTINUATION:
        # For CONTINUATION, we don't care if price is above/below mean,
        # as long as it's not EXTREMELY overextended against us.
        # Logic: If LONG and TREND_UP, we just need to ensure we aren't at +4.0Z
        if abs(z_score) > 3.5:
            passed = False
            reason = f"Extreme extension ({z_score:.2f}Z) unsafe for continuation"
        else:
            passed = True
            reason = f"Trend-aligned ({direction}) at {z_score:.2f}Z"
            score = 1.0
    else:
        # Traditional REVERSION Logic
        if side == "LONG":
            if z_score > -min_z:
                passed = False
                reason = f"Price at {z_score:.2f}Z (Too near mean for reversion)"
            else:
                score = 1.0 if z_score < -2.5 else 0.5
                reason = f"Price at {z_score:.2f}Z (Extreme reversion supported)"
        elif side == "SHORT":
            if z_score < min_z:
                passed = False
                reason = f"Price at {z_score:.2f}Z (Too near mean for reversion)"
            else:
                score = 1.0 if z_score > 2.5 else 0.5
                reason = f"Price at {z_score:.2f}Z (Extreme reversion supported)"

    metrics = {"z_score": round(z_score, 3), "price": current_price, "mode": setup_mode.value}

    return GuardianResult(
        passed=passed,
        score=score,
        multiplier=1.0,
        reason=reason,
        metrics=metrics,
        gate_name="STATISTICAL_LOCATION",
        setup_mode=setup_mode,
    )
