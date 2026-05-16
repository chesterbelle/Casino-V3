import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("SpreadSanityGuardian")


def check_spread_sanity(symbol: str, context_registry) -> GuardianResult:
    """
    Checks if the current spread is within acceptable limits for scalping.
    """
    if not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="SPREAD_SANITY")

    spread_data = getattr(context_registry, "spread_state", {}).get(symbol)
    if not spread_data:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="SPREAD_SANITY")

    current = spread_data.get("current", 0.0)
    avg_5m = spread_data.get("avg_5m", 0.0)
    metrics = {"current_spread": round(current, 6), "avg_5m": round(avg_5m, 6)}

    passed = True
    score = 1.0

    if avg_5m > 0:
        ratio = current / avg_5m
        if ratio > 2.0:
            passed = False
            score = 0.0
        elif ratio > 1.0:
            # Linear decay from 1.0 (at ratio=1) to 0.3 (at ratio=2)
            score = max(0.3, 1.0 - (ratio - 1.0) * 0.7)
        else:
            score = 1.0

    reason = "Wide spread spike" if not passed else "Spread analyzed"

    return GuardianResult(
        passed=passed,
        score=round(score, 3),
        multiplier=1.0,
        reason=reason,
        metrics=metrics,
        gate_name="SPREAD_SANITY",
    )
