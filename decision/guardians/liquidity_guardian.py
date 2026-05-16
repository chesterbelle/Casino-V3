import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("LiquidityGuardian")


def check_liquidity_heatmap(symbol: str, side: str, target_price: float, context_registry) -> GuardianResult:
    """
    Checks if there's enough liquidity at the target price.
    """
    if not context_registry:
        return GuardianResult(passed=True, score=1.0, gate_name="LIQUIDITY_HEATMAP")

    # target_price is usually the VAL/VAH or the entry level
    score = context_registry.get_liquidity_score(symbol, target_price, side)

    metrics = {
        "target_price": target_price,
        "score": score,
    }

    # This guardian is 'Soft' - it never blocks the trade by itself (passed=True)
    # unless we decide to make it a Hard Gate in the future.
    # For now, it just reduces confidence if we are 'trading into air'.

    return GuardianResult(
        passed=True,
        score=score,
        multiplier=1.0,
        reason="Liquidity support analyzed" if score > 0.5 else "Low liquidity support (trading into air)",
        metrics=metrics,
        gate_name="LIQUIDITY_HEATMAP",
    )
