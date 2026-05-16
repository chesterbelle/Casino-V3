from typing import Tuple

from .guardian_result import GuardianResult, SetupMode
from .liquidity_guardian import check_liquidity_heatmap
from .regime_guardian import check_regime_alignment
from .spread_sanity_guardian import check_spread_sanity


class GuardianManager:
    """
    Orchestrator for the Order Flow Guardians.
    Evaluates them sequentially and traces the result using UDT.
    """

    def __init__(self, trace_callback=None):
        self.trace_decision = trace_callback

    def evaluate_all(
        self, symbol: str, side: str, reversal_signal: dict, context_registry, recent_extremes: dict, trace=None
    ) -> Tuple[bool, float, SetupMode, str]:
        """
        Runs all guardians. Returns (passed, final_multiplier, mode, value_position).
        """
        results = []

        # 1. Execute all guardians
        results.append(check_regime_alignment(symbol, side, reversal_signal, context_registry))
        results.append(check_spread_sanity(symbol, context_registry))

        # Phase 3: Liquidity Guardian
        target_price = reversal_signal.get("close") or reversal_signal.get("price", 0.0)
        results.append(check_liquidity_heatmap(symbol, side, target_price, context_registry))

        # 2. Evaluation and UDT Logging
        final_mode = SetupMode.REVERSION
        for res in results:
            if trace:
                trace.add_step(component=res.gate_name, passed=res.passed, message=res.reason, metadata=res.metrics)

            if not res.passed:
                return False, 0.0, SetupMode.NEUTRAL, "UNKNOWN"

            if res.setup_mode == SetupMode.CONTINUATION:
                final_mode = SetupMode.CONTINUATION

        # 3. Aggregate Scoring
        total_score = sum(res.score for res in results) / len(results)
        final_multiplier = 1.0
        for res in results:
            final_multiplier *= res.multiplier
        final_multiplier *= total_score

        # 4. Final DNA Attribution
        if trace:
            trace.metadata.update(
                {
                    "total_score": round(total_score, 3),
                    "final_multiplier": round(final_multiplier, 3),
                    "final_mode": final_mode.value,
                }
            )

        # Extract value_position from regime guardian
        value_position = "OUT_OF_VALUE"
        for res in results:
            if res.gate_name == "REGIME_ALIGNMENT_V3" and res.metrics:
                value_position = res.metrics.get("value_position", "OUT_OF_VALUE")
                break

        return True, final_multiplier, final_mode, value_position

    def _trace(self, symbol: str, side: str, price: float, res: GuardianResult):
        status = "PASS" if res.passed else "REJECT"
        self.trace_decision(symbol, status, res.gate_name, res.reason, res.metrics, price, side)
