from typing import Tuple

from utils.trace_bullet import TraceBulletMixin

from .delta_divergence_guardian import check_delta_divergence
from .guardian_result import GuardianResult
from .poc_migration_guardian import check_poc_migration
from .regime_guardian import check_regime_alignment
from .spread_sanity_guardian import check_spread_sanity
from .va_integrity_guardian import check_va_integrity


class GuardianManager(TraceBulletMixin):
    """
    Orchestrator for the 6 Order Flow Guardians.
    Evaluates them sequentially and traces the result.
    """

    def __init__(self, trace_callback):
        super().__init__()
        self.trace_decision = trace_callback

    def evaluate_all(
        self, symbol: str, side: str, reversal_signal: dict, context_registry, recent_extremes: dict, fast_track: bool
    ) -> Tuple[bool, float]:
        """
        Runs all guardians. Returns (passed, final_multiplier).
        """
        multiplier = 1.0

        # Guardian 1: Regime Alignment
        res1 = check_regime_alignment(symbol, side, reversal_signal, context_registry, fast_track)
        self._trace(symbol, side, reversal_signal.get("close", 0.0), res1)
        self.trace(
            reversal_signal,
            f"GUARDIAN_CHECK:{res1.gate_name}",
            {"passed": res1.passed, "reason": res1.reason, "metrics": res1.metrics},
        )
        if not res1.passed:
            return False, 0.0
        multiplier *= res1.multiplier

        # Guardian 2: POC Migration
        res2 = check_poc_migration(symbol, side, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res2)
        self.trace(
            reversal_signal,
            f"GUARDIAN_CHECK:{res2.gate_name}",
            {"passed": res2.passed, "reason": res2.reason, "metrics": res2.metrics},
        )
        if not res2.passed:
            return False, 0.0
        multiplier *= res2.multiplier

        # Guardian 3: VA Integrity
        res3 = check_va_integrity(symbol, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res3)
        self.trace(
            reversal_signal,
            f"GUARDIAN_CHECK:{res3.gate_name}",
            {"passed": res3.passed, "reason": res3.reason, "metrics": res3.metrics},
        )
        if not res3.passed:
            return False, 0.0
        multiplier *= res3.multiplier

        # Guardian 5: Delta Divergence
        res5 = check_delta_divergence(symbol, side, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res5)
        self.trace(
            reversal_signal,
            f"GUARDIAN_CHECK:{res5.gate_name}",
            {"passed": res5.passed, "reason": res5.reason, "metrics": res5.metrics},
        )
        if not res5.passed:
            return False, 0.0

        # Guardian 6: Spread Sanity
        res6 = check_spread_sanity(symbol, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res6)
        self.trace(
            reversal_signal,
            f"GUARDIAN_CHECK:{res6.gate_name}",
            {"passed": res6.passed, "reason": res6.reason, "metrics": res6.metrics},
        )
        if not res6.passed:
            return False, 0.0

        return True, multiplier

    def _trace(self, symbol: str, side: str, price: float, res: GuardianResult):
        status = "PASS" if res.passed else "REJECT"
        self.trace_decision(symbol, status, res.gate_name, res.reason, res.metrics, price, side)
