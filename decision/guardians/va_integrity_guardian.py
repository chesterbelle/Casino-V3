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
        "integrity": integrity,
        "threshold": threshold,
        "critical_threshold": critical_threshold,
        "window": current_window,
    }

    if integrity < critical_threshold:
        logger.info(
            f"🛡️ [VA_INTEGRITY] {symbol} rejected: Integrity {integrity:.4f} critically low < {critical_threshold:.4f} ({current_window})"
        )
        return GuardianResult(
            passed=False, multiplier=0.0, reason="Critically low VA density", metrics=metrics, gate_name="VA_INTEGRITY"
        )

    if integrity < threshold:
        return GuardianResult(
            passed=True,
            multiplier=strat_config.LTA_SOFT_GATE_REDUCTION,
            reason="Soft VA density (sizing reduced)",
            metrics=metrics,
            gate_name="VA_INTEGRITY",
        )

    return GuardianResult(
        passed=True, multiplier=1.0, reason="Acceptable VA density", metrics=metrics, gate_name="VA_INTEGRITY"
    )
