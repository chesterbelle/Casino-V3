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

    # Get L2 ratio threshold from profile
    try:
        from decision.engine.profile_manager import profile_manager

        l2_ratio_min = profile_manager.get_guardian_params(symbol).get("l2_ratio_min", DEFAULT_L2_RATIO_MIN)
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
