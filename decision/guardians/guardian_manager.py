from typing import Tuple

from utils.trace_bullet import TraceBulletMixin

from .delta_divergence_guardian import check_delta_divergence
from .failed_auction_guardian import check_failed_auction
from .guardian_result import GuardianResult
from .liquidity_guardian import check_liquidity_heatmap
from .poc_migration_guardian import check_poc_migration
from .regime_guardian import check_regime_alignment
from .spread_sanity_guardian import check_spread_sanity
from .statistical_location_guardian import check_statistical_location
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
        Phase 2 Alpha: Transition to Confidence Scoring + Attribution.
        """
        results = []

        # 1. Execute all guardians
        results.append(check_regime_alignment(symbol, side, reversal_signal, context_registry, fast_track))
        results.append(check_poc_migration(symbol, side, context_registry, fast_track))
        results.append(check_va_integrity(symbol, context_registry, fast_track))
        results.append(check_delta_divergence(symbol, side, context_registry, fast_track))
        results.append(check_spread_sanity(symbol, context_registry, fast_track))

        # Phase 3 & D1: Location Guardians
        target_price = reversal_signal.get("close") or reversal_signal.get("price", 0.0)

        results.append(check_liquidity_heatmap(symbol, side, target_price, context_registry, fast_track))
        results.append(check_statistical_location(symbol, side, target_price, context_registry, fast_track))

        # Guardian 9: Failed Auction (Hypothesis Round 2)
        results.append(
            check_failed_auction(symbol, side, reversal_signal, context_registry, recent_extremes, fast_track)
        )

        # 2. Hard Gate Evaluation (Interpretability)
        for res in results:
            self._trace(symbol, side, reversal_signal.get("close", 0.0), res)
            if not res.passed:
                self.trace(
                    reversal_signal,
                    "GUARDIAN_REJECT",
                    {"gate": res.gate_name, "reason": res.reason, "metrics": res.metrics},
                )
                return False, 0.0

        # 3. Aggregate Scoring (Phase 2 Alpha)
        # We calculate total_confidence as the average score of all guardians
        total_score = sum(res.score for res in results) / len(results)

        # Sizing Multiplier is the product of individual multipliers * final confidence
        final_multiplier = 1.0
        for res in results:
            final_multiplier *= res.multiplier

        # Apply confidence-based sizing (Soft Sizing)
        # If confidence is low (e.g. 0.6), we reduce size by that factor
        final_multiplier *= total_score

        # 4. Detailed Attribution Trace (The "Crystal Layer" Observability)
        attribution = {res.gate_name: {"score": res.score, "multiplier": res.multiplier} for res in results}
        self.trace(
            reversal_signal,
            "GUARDIAN_BREAKDOWN",
            {
                "total_score": round(total_score, 3),
                "final_multiplier": round(final_multiplier, 3),
                "attribution": attribution,
            },
        )

        return True, final_multiplier

    def _trace(self, symbol: str, side: str, price: float, res: GuardianResult):
        status = "PASS" if res.passed else "REJECT"
        self.trace_decision(symbol, status, res.gate_name, res.reason, res.metrics, price, side)
