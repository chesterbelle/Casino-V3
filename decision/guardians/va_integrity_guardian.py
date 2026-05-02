import logging

import config.strategies as strat_config

from .guardian_result import GuardianResult

logger = logging.getLogger("VAIntegrityGuardian")


def check_va_integrity(symbol: str, context_registry, fast_track: bool) -> GuardianResult:
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="VA_INTEGRITY")

    integrity = context_registry.get_va_integrity(symbol)

    current_window = getattr(context_registry, "current_window", {}).get(symbol, "")
    va_thresholds = getattr(strat_config, "LTA_VA_INTEGRITY_BY_WINDOW", {})
    threshold = va_thresholds.get(current_window, strat_config.LTA_VA_INTEGRITY_MIN)

    critical_threshold = threshold * 0.50

    metrics = {
        "integrity": round(integrity, 5),
        "threshold": threshold,
        "critical_threshold": critical_threshold,
        "window": current_window,
    }
    
    passed = True
    score = 1.0

    if integrity < critical_threshold:
        passed = False
        score = 0.0
    elif integrity < threshold:
        # Linear score between 0.3 and 1.0
        range_size = threshold - critical_threshold
        if range_size > 0:
            normalized = (integrity - critical_threshold) / range_size
            score = 0.3 + (normalized * 0.7)
        else:
            score = 0.3
    else:
        score = 1.0

    reason = "Critically low VA density" if not passed else "VA density analyzed"
    
    return GuardianResult(
        passed=passed,
        score=round(score, 3),
        multiplier=1.0, # We use score instead of hard-coded reduction
        reason=reason,
        metrics=metrics,
        gate_name="VA_INTEGRITY",
    )
