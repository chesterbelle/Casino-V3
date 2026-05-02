from typing import Tuple

from .delta_divergence_guardian import check_delta_divergence
from .guardian_result import GuardianResult
from .poc_migration_guardian import check_poc_migration
from .regime_guardian import check_regime_alignment
from .spread_sanity_guardian import check_spread_sanity
from .va_integrity_guardian import check_va_integrity


class GuardianManager:
    """
    Orchestrator for the 6 Order Flow Guardians.
    Evaluates them sequentially and traces the result.
    """

    def __init__(self, trace_callback):
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
        if not res1.passed:
            return False, 0.0
        multiplier *= res1.multiplier

        # Guardian 2: POC Migration
        res2 = check_poc_migration(symbol, side, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res2)
        if not res2.passed:
            return False, 0.0
        multiplier *= res2.multiplier

        # Guardian 3: VA Integrity
        res3 = check_va_integrity(symbol, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res3)
        if not res3.passed:
            return False, 0.0
        multiplier *= res3.multiplier

        # Guardian 4: REMOVED in Phase 2300 — Failed Auction
        # Concept operates at session timeframe (hours), not 1m candles.
        # Keeping it caused inverted discrimination (-29% in trending conditions).
        # res4 = check_failed_auction(symbol, side, reversal_signal, context_registry, recent_extremes, fast_track)
        # self._trace(symbol, side, reversal_signal.get("close", 0.0), res4)
        # if not res4.passed: return False, 0.0

        # Guardian 5: Delta Divergence
        res5 = check_delta_divergence(symbol, side, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res5)
        if not res5.passed:
            return False, 0.0

        # Guardian 6: Spread Sanity
        res6 = check_spread_sanity(symbol, context_registry, fast_track)
        self._trace(symbol, side, 0.0, res6)
        if not res6.passed:
            return False, 0.0

        return True, multiplier

    def _trace(self, symbol: str, side: str, price: float, res: GuardianResult):
        status = "PASS" if res.passed else "REJECT"
        self.trace_decision(symbol, status, res.gate_name, res.reason, res.metrics, price, side)
