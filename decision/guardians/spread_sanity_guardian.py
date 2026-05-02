import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("SpreadSanityGuardian")


def check_spread_sanity(symbol: str, context_registry, fast_track: bool) -> GuardianResult:
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="SPREAD_SANITY")

    spread_data = getattr(context_registry, "spread_state", {}).get(symbol)
    if not spread_data:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="SPREAD_SANITY")

    current = spread_data.get("current", 0.0)
    avg_5m = spread_data.get("avg_5m", 0.0)
    metrics = {"current_spread": current, "avg_5m": avg_5m}

    if avg_5m > 0 and current > avg_5m * 2.0:
        logger.info(f"🛡️ [SPREAD_SANITY] {symbol} rejected: Spread {current:.6f} > 2x avg {avg_5m:.6f}")
        return GuardianResult(
            passed=False, multiplier=0.0, reason="Wide spread", metrics=metrics, gate_name="SPREAD_SANITY"
        )

    return GuardianResult(
        passed=True, multiplier=1.0, reason="Normal spread", metrics=metrics, gate_name="SPREAD_SANITY"
    )
