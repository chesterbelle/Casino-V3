import logging

from .guardian_result import GuardianResult, SetupMode

logger = logging.getLogger("StructureGuardian")


def check_structure_alignment(
    symbol: str, price: float, side: str, setup_mode: SetupMode, context_registry
) -> GuardianResult:
    """
    V10.3 Structure Guardian: Evaluates micro-geography against the Volume Profile.

    Prevents toxic flow by enforcing that setups are executed in high-probability
    structural areas (VAH/VAL for reversions, POC for continuations).
    """
    if not context_registry or price <= 0:
        return GuardianResult(passed=True, score=1.0, gate_name="STRUCTURE_GEOGRAPHY")

    # Get structural nodes
    poc, vah, val = context_registry.get_structural(symbol)

    if poc == 0.0 or vah == 0.0 or val == 0.0:
        # Missing data, allow but penalize slightly
        return GuardianResult(
            passed=True, score=0.8, reason="Missing Volume Profile data", gate_name="STRUCTURE_GEOGRAPHY"
        )

    va_width = vah - val
    if va_width <= 0:
        return GuardianResult(passed=True, score=1.0, reason="Invalid VA Width", gate_name="STRUCTURE_GEOGRAPHY")

    # Tolerance is 15% of the Value Area width
    tolerance = max(va_width * 0.15, price * 0.001)

    geo_tag = "NO_MANS_LAND"
    if abs(price - vah) <= tolerance:
        geo_tag = "AT_VAH"
    elif abs(price - val) <= tolerance:
        geo_tag = "AT_VAL"
    elif abs(price - poc) <= tolerance:
        geo_tag = "AT_POC"

    metrics = {
        "price": price,
        "poc": poc,
        "vah": vah,
        "val": val,
        "tolerance": tolerance,
        "geography": geo_tag,
        "setup_mode": setup_mode.name,
    }

    # -------------------------------------------------------------------------
    # DECISION MATRIX BY SETUP MODE
    # -------------------------------------------------------------------------

    if setup_mode == SetupMode.REVERSION:
        if geo_tag in ("AT_VAH", "AT_VAL"):
            # Ensure proper side at edges if possible, but AT_VAH/VAL is generally good for reversion
            if (geo_tag == "AT_VAH" and side == "LONG") or (geo_tag == "AT_VAL" and side == "SHORT"):
                # Reverting OUTWARDS from the value area is extremely dangerous (breakout failure)
                # We want to fade the edge, not buy the top
                return GuardianResult(
                    passed=False,
                    score=0.0,
                    reason=f"BLOCKED (FADE RISK) | Reverting outwards {side} at {geo_tag}",
                    metrics=metrics,
                    gate_name="STRUCTURE_GEOGRAPHY",
                )

            return GuardianResult(
                passed=True,
                score=1.0,
                reason=f"PASSED | Strong reversion context at {geo_tag}",
                metrics=metrics,
                gate_name="STRUCTURE_GEOGRAPHY",
            )

        elif geo_tag == "AT_POC":
            return GuardianResult(
                passed=False,
                score=0.0,
                reason="BLOCKED (TOXIC FLOW) | Reversion is noise AT_POC",
                metrics=metrics,
                gate_name="STRUCTURE_GEOGRAPHY",
            )

        else:  # NO_MANS_LAND
            return GuardianResult(
                passed=True,
                score=0.3,
                reason="PASSED (PENALIZED) | Reversion in NO_MANS_LAND has low predictive value",
                metrics=metrics,
                gate_name="STRUCTURE_GEOGRAPHY",
            )

    elif setup_mode == SetupMode.CONTINUATION:
        if geo_tag == "AT_POC":
            return GuardianResult(
                passed=True,
                score=1.0,
                reason="PASSED | Continuation from fair value (POC Pullback)",
                metrics=metrics,
                gate_name="STRUCTURE_GEOGRAPHY",
            )

        elif geo_tag in ("AT_VAH", "AT_VAL"):
            return GuardianResult(
                passed=False,
                score=0.0,
                reason="BLOCKED (FADE RISK) | Continuation is unsafe at VA Edge without acceptance",
                metrics=metrics,
                gate_name="STRUCTURE_GEOGRAPHY",
            )

        else:  # NO_MANS_LAND
            return GuardianResult(
                passed=True,
                score=0.7,
                reason="PASSED | Continuation in NO_MANS_LAND",
                metrics=metrics,
                gate_name="STRUCTURE_GEOGRAPHY",
            )

    # Default
    return GuardianResult(
        passed=True, score=0.5, reason="Unknown setup mode", metrics=metrics, gate_name="STRUCTURE_GEOGRAPHY"
    )
