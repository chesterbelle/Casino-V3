import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("LiquidityGuardian")

# Default L2 ratio minimum (used if no profile loaded)
DEFAULT_L2_RATIO_MIN = 2.0


def check_liquidity_heatmap(symbol: str, side: str, target_price: float, context_registry) -> GuardianResult:
    """
    Checks if there's enough liquidity at the target price.
    Uses profile-specific L2 ratio threshold.
    """
    if not context_registry:
        return GuardianResult(passed=True, score=1.0, gate_name="LIQUIDITY_HEATMAP")

    score = context_registry.get_liquidity_score(symbol, target_price, side)
    metrics = {
        "target_price": target_price,
        "score": score,
    }

    l2_ratio = context_registry.get_l2_ratio(symbol, side)
    metrics["l2_ratio"] = l2_ratio

    # Get L2 ratio threshold from profile (dynamic based on macro direction)
    try:
        from decision.engine.profile_manager import profile_manager

        guardian_params = profile_manager.get_guardian_params(symbol)

        # Read macro layer direction directly from regime data
        # This is more reliable than waiting for regime classification
        # BULL/RANGE: Thin Wall (l2_ratio_min) works better
        # BEAR (macro DOWN): High Wall (l2_ratio_min_trend_down) works better
        regime_v2_data = getattr(context_registry, "_regime_v2", {}).get(symbol)

        # Extract macro direction and score from regime data
        macro_direction = "NEUTRAL"
        macro_score = 0.0
        if regime_v2_data and "layers" in regime_v2_data:
            macro_layer = regime_v2_data["layers"].get("macro", {})
            macro_direction = macro_layer.get("vote", "NEUTRAL")
            macro_score = macro_layer.get("score", 0.0)

        # Use macro direction directly for l2_ratio_min decision
        macro_threshold = guardian_params.get("macro_threshold", 0.6)  # Minimum macro score to activate High Wall

        if macro_direction == "DOWN" and macro_score >= macro_threshold:
            l2_ratio_min = guardian_params.get(
                "l2_ratio_min_trend_down", guardian_params.get("l2_ratio_min", DEFAULT_L2_RATIO_MIN)
            )
        else:
            l2_ratio_min = guardian_params.get("l2_ratio_min", DEFAULT_L2_RATIO_MIN)

    except Exception:
        l2_ratio_min = DEFAULT_L2_RATIO_MIN

    # Hardened L2 Wall Requirement for Adverse Excursion (MAE) Reduction
    if l2_ratio < l2_ratio_min:
        return GuardianResult(
            passed=False,
            score=0.0,
            multiplier=0.0,
            reason=f"BLOCKED (THIN WALL) | L2 Ratio {l2_ratio:.2f} < {l2_ratio_min}",
            metrics=metrics,
            gate_name="LIQUIDITY_HEATMAP",
        )

    return GuardianResult(
        passed=True,
        score=score,
        multiplier=1.0,
        reason="Liquidity support analyzed" if score > 0.5 else "Low liquidity support (trading into air)",
        metrics=metrics,
        gate_name="LIQUIDITY_HEATMAP",
    )
