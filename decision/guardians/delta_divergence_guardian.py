import logging

from .guardian_result import GuardianResult

logger = logging.getLogger("DeltaDivergenceGuardian")


def check_delta_divergence(symbol: str, side: str, context_registry, fast_track: bool) -> GuardianResult:
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="DELTA_DIVERGENCE")

    state = context_registry.micro_state.get(symbol)
    if not state:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="DELTA_DIVERGENCE")

    z_score = state.get("z_score", 0.0)
    metrics = {"z_score": z_score, "threshold": 2.5}

    if side == "LONG":
        if z_score < -2.5:
            logger.info(f"🛡️ [DELTA_DIVERGENCE] {symbol} LONG blocked: Extreme selling flow (Z: {z_score:.2f})")
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason="Orderflow pressure too high",
                metrics=metrics,
                gate_name="DELTA_DIVERGENCE",
            )

    if side == "SHORT":
        if z_score > 2.5:
            logger.info(f"🛡️ [DELTA_DIVERGENCE] {symbol} SHORT blocked: Extreme buying flow (Z: {z_score:.2f})")
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason="Orderflow pressure too high",
                metrics=metrics,
                gate_name="DELTA_DIVERGENCE",
            )

    return GuardianResult(
        passed=True,
        multiplier=1.0,
        reason="Orderflow supportive/neutral",
        metrics=metrics,
        gate_name="DELTA_DIVERGENCE",
    )
