import logging

from .guardian_result import GuardianResult, SetupMode

logger = logging.getLogger("RegimeGuardian")

# V4 Regime: Value Position via Volume Profile (POC/VAH/VAL)
# VWAP Z is lagging; Volume Profile reflects actual auction consensus.
VA_EXCESS_FACTOR = 0.5  # Price beyond VAH/VAL + 50% of VA width = EXCESS


def determine_value_position(price, poc, vah, val, context_registry, symbol, z_score_fallback=0.0):
    """
    Calculate Value Position from Volume Profile geometry.

    Returns: "IN_VALUE" | "OUT_OF_VALUE" | "EXCESS"
    """
    # Primary: Volume Profile (POC/VAH/VAL)
    if poc > 0 and vah > val:
        va_width = vah - val
        if price <= val:
            return "EXCESS" if price < val - (va_width * VA_EXCESS_FACTOR) else "OUT_OF_VALUE"
        elif price >= vah:
            return "EXCESS" if price > vah + (va_width * VA_EXCESS_FACTOR) else "OUT_OF_VALUE"
        else:
            return "IN_VALUE"

    # Fallback: VWAP Z-score (legacy)
    if price > 0 and context_registry:
        vwap_z = context_registry.get_vwap_zscore(symbol, price)
        if vwap_z == 0.0:
            vwap_z = z_score_fallback
        abs_z = abs(vwap_z)
        if abs_z >= 3.0:
            return "EXCESS"
        elif abs_z >= 2.0:
            return "OUT_OF_VALUE"
        else:
            return "IN_VALUE"

    # No data available
    return "IN_VALUE"


def _check_trend_regime(regime_v2, direction, side, value_acceptance, value_position, confidence, metrics):
    """
    Handle TREND regime decision matrix (7 cases).

    Returns GuardianResult or None if no case matches.
    """
    is_trend_aligned = (direction == "UP" and side == "LONG") or (direction == "DOWN" and side == "SHORT")
    is_counter_trend = (direction == "UP" and side == "SHORT") or (direction == "DOWN" and side == "LONG")

    # Case 1: TREND + trend-aligned + ACCEPTING → CONTINUATION
    if is_trend_aligned and value_acceptance == "ACCEPTING":
        return GuardianResult(
            passed=True,
            score=1.0,
            reason=f"IMBALANCE | {regime_v2} dir={direction} side={side} ({value_position}) → CONTINUATION",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=SetupMode.CONTINUATION,
        )

    # Case 2: TREND + trend-aligned + NEUTRAL → CONTINUATION (lower confidence)
    if is_trend_aligned and value_acceptance == "NEUTRAL":
        return GuardianResult(
            passed=True,
            score=0.7,
            reason=f"IMBALANCE (weak) | {regime_v2} dir={direction} side={side} ({value_position}) → CONTINUATION",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=SetupMode.CONTINUATION,
        )

    # Case 3: TREND + counter-trend + REJECTING + EXCESS → REVERSION
    if is_counter_trend and value_acceptance == "REJECTING" and value_position == "EXCESS":
        return GuardianResult(
            passed=True,
            score=0.8,
            reason=f"EXCESS | {regime_v2} absorption at VA extreme → REVERSION",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=SetupMode.REVERSION,
        )

    # Case 4: TREND + counter-trend + REJECTING + OUT_OF_VALUE → REVERSION (lower confidence)
    if is_counter_trend and value_acceptance == "REJECTING" and value_position == "OUT_OF_VALUE":
        return GuardianResult(
            passed=True,
            score=0.5,
            reason=f"OUT_OF_VALUE (weak) | {regime_v2} absorption outside VA → REVERSION",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=SetupMode.REVERSION,
        )

    # Case 5: TREND + counter-trend + ACCEPTING → BLOCK
    if is_counter_trend and value_acceptance == "ACCEPTING":
        return GuardianResult(
            passed=False,
            score=0.0,
            reason=f"BLOCKED | {regime_v2} accepting new prices, counter-trend {side} rejected",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
        )

    # Case 6: TREND + counter-trend + NEUTRAL → BLOCK (high conf) or ALLOW (low conf)
    if is_counter_trend:
        if confidence > 0.3:
            return GuardianResult(
                passed=False,
                score=0.0,
                reason=f"BLOCKED | {regime_v2} (conf={confidence:.2f}), counter-trend {side} rejected",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
            )
        return GuardianResult(
            passed=True,
            score=max(0.1, 1.0 - confidence),
            reason=f"WEAK TREND | {regime_v2} (conf={confidence:.2f}), counter-trend allowed with penalty",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=SetupMode.REVERSION,
        )

    # Case 7: TREND + trend-aligned + REJECTING → CONTINUATION (pullback entry)
    if is_trend_aligned and value_acceptance == "REJECTING":
        return GuardianResult(
            passed=True,
            score=0.6,
            reason=f"IMBALANCE (absorption) | {regime_v2} ({value_position}) → CONTINUATION (pullback entry)",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=SetupMode.CONTINUATION,
        )

    return None


def check_regime_alignment(symbol: str, side: str, reversal_signal: dict, context_registry) -> GuardianResult:
    """
    V4 Regime Guardian: Value Position x Value Acceptance model.

    Decision Matrix:
        |                | ACCEPTING (new value) | REJECTING (absorption) |
        | IN_VALUE       | BALANCE → REVERSION   | BALANCE → REVERSION    |
        | OUT_OF_VALUE   | IMBALANCE → CONTINUATION | EXCESS → REVERSION  |
    """
    if not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="REGIME_ALIGNMENT")

    # Read V2 regime data from MarketRegimeSensor
    regime_v2_data = getattr(context_registry, "_regime_v2", {}).get(symbol)
    if not regime_v2_data:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="REGIME_ALIGNMENT", reason="No regime data")

    regime_v2 = regime_v2_data.get("regime", "BALANCE")
    direction = regime_v2_data.get("direction", "NEUTRAL")
    confidence = regime_v2_data.get("confidence", 0.0)
    value_acceptance = regime_v2_data.get("value_acceptance", "NEUTRAL")

    # Determine Value Position from Volume Profile
    price = reversal_signal.get("close", 0.0) or reversal_signal.get("price", 0.0)
    poc, vah, val = context_registry.get_structural(symbol) if context_registry else (0.0, 0.0, 0.0)
    z_score_fb = reversal_signal.get("z_score", 0.0)
    value_position = determine_value_position(price, poc, vah, val, context_registry, symbol, z_score_fb)

    # Build metrics dict
    metrics = {
        "regime": regime_v2,
        "direction": direction,
        "confidence": confidence,
        "value_position": value_position,
        "value_acceptance": value_acceptance,
        "poc": round(poc, 4),
        "vah": round(vah, 4),
        "val": round(val, 4),
        "footprint_z_score": z_score_fb,
        "side": side,
    }

    # Determine tactical type for setup mode
    tactical_type = reversal_signal.get("tactical_type", reversal_signal.get("setup_type", ""))

    # BALANCE regime
    if regime_v2 == "BALANCE":
        is_pure_reversion = tactical_type in (
            "TacticalAbsorptionV2",
            "FailedBreakout",
            "failed_breakout",
            "LiquidityExhaustion",
            "liquidity_exhaustion",
            "AMT_FAILED_BREAKOUT",
            "AMT_LIQUIDITY_EXHAUSTION",
        )
        if value_position in ("OUT_OF_VALUE", "EXCESS"):
            return GuardianResult(
                passed=True,
                score=1.0,
                reason=f"BALANCE | price@{price:.2f} ({value_position}, VA={val:.2f}-{vah:.2f}) → REVERSION",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.REVERSION,
            )
        mode = SetupMode.REVERSION if is_pure_reversion else SetupMode.CONTINUATION
        reason_str = "PURE REVERSION" if mode == SetupMode.REVERSION else "CONTINUATION (rotation)"
        return GuardianResult(
            passed=True,
            score=0.7,
            reason=f"BALANCE | price@{price:.2f} ({value_position}, VA={val:.2f}-{vah:.2f}) → {reason_str}",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=mode,
        )

    # TREND regime
    if regime_v2 in ("TREND_UP", "TREND_DOWN"):
        result = _check_trend_regime(regime_v2, direction, side, value_acceptance, value_position, confidence, metrics)
        if result:
            return result

    # Fallback
    return GuardianResult(
        passed=True,
        score=0.5,
        reason=f"DEFAULT BALANCE | regime={regime_v2} dir={direction} ({value_position})",
        metrics=metrics,
        gate_name="REGIME_ALIGNMENT_V3",
        setup_mode=SetupMode.REVERSION,
    )
