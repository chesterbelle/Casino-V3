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
    metrics = {"z_score": round(z_score, 3), "threshold": 2.5}
    score = 1.0
    passed = True

    # Scoring Logic:
    # We want a high score (1.0) if orderflow is neutral or supportive.
    # We want a low score (0.0-0.5) if orderflow is slightly against us.
    # We REJECT (passed=False) only if pressure is extreme (> 2.5).

    if side == "LONG":
        if z_score < -2.5:
            passed = False
            score = 0.0
        elif z_score < 0:
            # Linear decay from 1.0 (at Z=0) to 0.0 (at Z=-2.5)
            score = max(0.0, 1.0 + (z_score / 2.5))
        else:
            # Supportive buying flow for a LONG
            score = 1.0
            
    elif side == "SHORT":
        if z_score > 2.5:
            passed = False
            score = 0.0
        elif z_score > 0:
            # Linear decay from 1.0 (at Z=0) to 0.0 (at Z=2.5)
            score = max(0.0, 1.0 - (z_score / 2.5))
        else:
            # Supportive selling flow for a SHORT
            score = 1.0

    reason = "Orderflow pressure too high" if not passed else "Orderflow analyzed"
    
    return GuardianResult(
        passed=passed,
        score=round(score, 3),
        multiplier=1.0,
        reason=reason,
        metrics=metrics,
        gate_name="DELTA_DIVERGENCE",
    )
