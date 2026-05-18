import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("LiquidityGuardian")


def check_liquidity_heatmap(symbol: str, side: str, target_price: float, context_registry) -> GuardianResult:
    """
    Checks if there's enough liquidity at the target price.
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

    # Hardened L2 Wall Requirement for Adverse Excursion (MAE) Reduction
    # A High Wall (>2.0) acts as an active physical shield, cutting average MAE to 0.358%.
    if l2_ratio < 2.0:
        return GuardianResult(
            passed=False,
            score=0.0,
            multiplier=0.0,
            reason=f"BLOCKED (THIN WALL) | L2 Ratio {l2_ratio:.2f} < 2.0",
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
