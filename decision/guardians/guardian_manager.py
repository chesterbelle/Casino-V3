from typing import Tuple

from utils.trace_bullet import TraceBulletMixin

from .guardian_result import GuardianResult, SetupMode
from .liquidity_guardian import check_liquidity_heatmap
from .regime_guardian import check_regime_alignment
from .spread_sanity_guardian import check_spread_sanity
from .statistical_location_guardian import check_statistical_location


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
    ) -> Tuple[bool, float, SetupMode, str]:
        """
        Runs all guardians. Returns (passed, final_multiplier, mode, value_position).
        Phase V3: Opportunity Classification (Reversion vs Continuation).
        """
        results = []

        # 1. Execute all guardians
        results.append(check_regime_alignment(symbol, side, reversal_signal, context_registry, fast_track))
        results.append(check_spread_sanity(symbol, context_registry, fast_track))

        # Phase 3 & D1: Location Guardians
        target_price = reversal_signal.get("close") or reversal_signal.get("price", 0.0)

        results.append(check_liquidity_heatmap(symbol, side, target_price, context_registry, fast_track))
        results.append(check_statistical_location(symbol, side, target_price, context_registry, fast_track))

        # 2. Hard Gate Evaluation (Interpretability)
        final_mode = SetupMode.REVERSION
        for res in results:
            self._trace(symbol, side, reversal_signal.get("close", 0.0), res)
            if not res.passed:
                self.trace(
                    reversal_signal,
                    "GUARDIAN_REJECT",
                    {"gate": res.gate_name, "reason": res.reason, "metrics": res.metrics},
                )
                return False, 0.0, SetupMode.NEUTRAL, "UNKNOWN"

            # V3: Aggregate Mode (Priority to Continuation if alignment says so)
            if res.setup_mode == SetupMode.CONTINUATION:
                final_mode = SetupMode.CONTINUATION

        # 3. Aggregate Scoring (Phase 2 Alpha)
        total_score = sum(res.score for res in results) / len(results)

        # Sizing Multiplier is the product of individual multipliers * final confidence
        final_multiplier = 1.0
        for res in results:
            final_multiplier *= res.multiplier

        # Apply confidence-based sizing (Soft Sizing)
        final_multiplier *= total_score

        # 4. Detailed Attribution Trace (The "Crystal Layer" Observability)
        attribution = {
            res.gate_name: {
                "score": res.score,
                "multiplier": res.multiplier,
                "mode": res.setup_mode.value,
                "reason": res.reason,
            }
            for res in results
        }

        # Extract V3 regime context for top-level trace (if available)
        regime_context = {}
        for res in results:
            if res.gate_name == "REGIME_ALIGNMENT_V3" and res.metrics:
                regime_context = {
                    "value_position": res.metrics.get("value_position"),
                    "value_acceptance": res.metrics.get("value_acceptance"),
                    "absorption_detected": res.metrics.get("absorption_detected"),
                    "vwap_z_score": res.metrics.get("vwap_z_score"),
                    "footprint_z_score": res.metrics.get("footprint_z_score"),
                }
                break
        self.trace(
            reversal_signal,
            "GUARDIAN_BREAKDOWN",
            {
                "total_score": round(total_score, 3),
                "final_multiplier": round(final_multiplier, 3),
                "final_mode": final_mode.value,
                "attribution": attribution,
                **regime_context,
            },
        )

        # Extract value_position from regime guardian for target calculation
        value_position = "OUT_OF_VALUE"
        for res in results:
            if res.gate_name == "REGIME_ALIGNMENT_V3" and res.metrics:
                value_position = res.metrics.get("value_position", "OUT_OF_VALUE")
                break

        return True, final_multiplier, final_mode, value_position

    def _trace(self, symbol: str, side: str, price: float, res: GuardianResult):
        status = "PASS" if res.passed else "REJECT"
        self.trace_decision(symbol, status, res.gate_name, res.reason, res.metrics, price, side)
