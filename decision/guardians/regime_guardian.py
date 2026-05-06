import logging

from .guardian_result import GuardianResult, SetupMode

logger = logging.getLogger("RegimeGuardian")

# V3 Regime: Value Position × Value Acceptance thresholds
Z_IN_VALUE = 2.0  # |Z| < 2.0 = price inside Value Area
Z_EXCESS = 3.0  # |Z| >= 3.0 = extreme dislocation (EXCESS)


def check_regime_alignment(
    symbol: str, side: str, reversal_signal: dict, context_registry, fast_track: bool
) -> GuardianResult:
    """
    V3 Regime Guardian: Value Position × Value Acceptance model.

    Replaces the old speed-based regime with a structural model:
    - Value Position: Where is price relative to VWAP (Z-score)?
    - Value Acceptance: Is the market accepting or rejecting new prices?

    Decision Matrix:
        |                | ACCEPTING (new value) | REJECTING (absorption) |
        | IN_VALUE       | BALANCE → REVERSION   | BALANCE → REVERSION    |
        | OUT_OF_VALUE   | IMBALANCE → CONTINUATION | EXCESS → REVERSION  |

    Key changes from V2:
    - NO "Local Consensus Override" — structural position dominates
    - NO TRANSITION state — either conviction exists or it doesn't
    - Counter-trend trades BLOCKED unless absorption detected (REJECTING + OUT_OF_VALUE)
    """
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="REGIME_ALIGNMENT")

    # Phase 2100: Read V2 regime data from MarketRegimeSensor
    regime_v2_data = getattr(context_registry, "_regime_v2", {}).get(symbol)
    if not regime_v2_data:
        # Legacy fallback
        return _legacy_check(symbol, side, context_registry)

    regime_v2 = regime_v2_data.get("regime", "BALANCE")
    direction = regime_v2_data.get("direction", "NEUTRAL")
    confidence = regime_v2_data.get("confidence", 0.0)
    value_acceptance = regime_v2_data.get("value_acceptance", "NEUTRAL")
    absorption_detected = regime_v2_data.get("absorption_detected", False)
    layers = regime_v2_data.get("layers", {})

    # Get Z-score for Value Position determination
    z_score = reversal_signal.get("z_score", 0.0)
    if z_score == 0.0:
        # Fallback: compute from VWAP state
        price = reversal_signal.get("close", 0.0) or reversal_signal.get("price", 0.0)
        if price > 0 and context_registry:
            z_score = context_registry.get_vwap_zscore(symbol, price)

    abs_z = abs(z_score)

    # Determine Value Position
    if abs_z >= Z_EXCESS:
        value_position = "EXCESS"
    elif abs_z >= Z_IN_VALUE:
        value_position = "OUT_OF_VALUE"
    else:
        value_position = "IN_VALUE"

    # Determine if side is trend-aligned or counter-trend
    is_trend_aligned = (direction == "UP" and side == "LONG") or (direction == "DOWN" and side == "SHORT")
    is_counter_trend = (direction == "UP" and side == "SHORT") or (direction == "DOWN" and side == "LONG")

    metrics = {
        "regime": regime_v2,
        "direction": direction,
        "confidence": confidence,
        "value_position": value_position,
        "value_acceptance": value_acceptance,
        "absorption_detected": absorption_detected,
        "z_score": round(z_score, 2),
        "side": side,
        "layers": {k: v.get("vote") if isinstance(v, dict) else v for k, v in layers.items()},
    }

    # =========================================================================
    # DECISION MATRIX: Value Position × Value Acceptance
    # =========================================================================

    # --- BALANCE: Reversion is the natural trade, but edge depends on value_position
    if regime_v2 == "BALANCE":
        # BALANCE + OUT_OF_VALUE: Price at extreme in a range → strong reversion edge
        if value_position in ("OUT_OF_VALUE", "EXCESS"):
            return GuardianResult(
                passed=True,
                score=1.0,
                reason=f"BALANCE | Z={z_score:.1f} ({value_position}) → REVERSION",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.REVERSION,
            )
        # BALANCE + IN_VALUE: Price near VWAP → weak reversion edge (target too close)
        # Statistical Location Guardian will likely block these anyway
        return GuardianResult(
            passed=True,
            score=0.5,
            reason=f"BALANCE | Z={z_score:.1f} ({value_position}) → REVERSION (weak edge)",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
            setup_mode=SetupMode.REVERSION,
        )

    # --- TREND: Price OUT_OF_VALUE → check Value Acceptance
    if regime_v2 in ("TREND_UP", "TREND_DOWN"):

        # Case 1: TREND + trend-aligned side + ACCEPTING → CONTINUATION
        # Market is accepting new prices, ride the trend on pullbacks
        if is_trend_aligned and value_acceptance == "ACCEPTING":
            return GuardianResult(
                passed=True,
                score=1.0,
                reason=f"IMBALANCE | {regime_v2} dir={direction} side={side} Z={z_score:.1f} → CONTINUATION",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.CONTINUATION,
            )

        # Case 2: TREND + trend-aligned side + NEUTRAL acceptance → CONTINUATION (lower confidence)
        # Trend exists but acceptance not confirmed — still prefer continuation
        if is_trend_aligned and value_acceptance == "NEUTRAL":
            return GuardianResult(
                passed=True,
                score=0.7,
                reason=f"IMBALANCE (weak) | {regime_v2} dir={direction} side={side} Z={z_score:.1f} → CONTINUATION",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.CONTINUATION,
            )

        # Case 3: TREND + counter-trend + REJECTING (absorption) + EXCESS → REVERSION
        # Market tried to extend but absorption detected at extreme — reversal likely
        if is_counter_trend and value_acceptance == "REJECTING" and value_position == "EXCESS":
            return GuardianResult(
                passed=True,
                score=0.8,
                reason=f"EXCESS | {regime_v2} absorption at Z={z_score:.1f} → REVERSION",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.REVERSION,
            )

        # Case 4: TREND + counter-trend + REJECTING + OUT_OF_VALUE → REVERSION (lower confidence)
        if is_counter_trend and value_acceptance == "REJECTING" and value_position == "OUT_OF_VALUE":
            return GuardianResult(
                passed=True,
                score=0.5,
                reason=f"EXCESS (weak) | {regime_v2} absorption at Z={z_score:.1f} → REVERSION",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.REVERSION,
            )

        # Case 5: TREND + counter-trend + ACCEPTING → BLOCK
        # Market is accepting new prices — counter-trend is suicide
        if is_counter_trend and value_acceptance == "ACCEPTING":
            return GuardianResult(
                passed=False,
                score=0.0,
                reason=f"BLOCKED | {regime_v2} accepting new prices, counter-trend {side} rejected",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
            )

        # Case 6: TREND + counter-trend + NEUTRAL → BLOCK (high confidence) or ALLOW (low confidence)
        # In a trend with neutral acceptance, counter-trend is dangerous
        if is_counter_trend:
            if confidence > 0.3:
                return GuardianResult(
                    passed=False,
                    score=0.0,
                    reason=f"BLOCKED | {regime_v2} (conf={confidence:.2f}), counter-trend {side} rejected",
                    metrics=metrics,
                    gate_name="REGIME_ALIGNMENT_V3",
                )
            # Weak trend: allow counter-trend reversion with low score
            return GuardianResult(
                passed=True,
                score=max(0.1, 1.0 - confidence),
                reason=f"WEAK TREND | {regime_v2} (conf={confidence:.2f}), counter-trend allowed with penalty",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.REVERSION,
            )

        # Case 7: TREND + trend-aligned + REJECTING (absorption at extreme)
        # Absorption detected but trend-aligned — this is a pullback, still continuation
        if is_trend_aligned and value_acceptance == "REJECTING":
            return GuardianResult(
                passed=True,
                score=0.6,
                reason=f"IMBALANCE (absorption) | {regime_v2} Z={z_score:.1f} → CONTINUATION (pullback entry)",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.CONTINUATION,
            )

    # Fallback: BALANCE (should not reach here)
    return GuardianResult(
        passed=True,
        score=0.5,
        reason=f"DEFAULT BALANCE | regime={regime_v2} dir={direction} Z={z_score:.1f}",
        metrics=metrics,
        gate_name="REGIME_ALIGNMENT_V3",
        setup_mode=SetupMode.REVERSION,
    )


def _legacy_check(symbol: str, side: str, context_registry) -> GuardianResult:
    """Legacy fallback when V2 regime data is not available."""
    regime = context_registry.get_regime(symbol)
    otf = getattr(context_registry, "otf", {}).get(symbol, "NEUTRAL")
    metrics = {"regime": regime, "otf": otf, "side": side, "source": "legacy_otf"}

    if regime == "NEUTRAL" or otf == "NEUTRAL":
        return GuardianResult(
            passed=True, multiplier=1.0, reason="Neutral regime (legacy)", metrics=metrics, gate_name="REGIME_ALIGNMENT"
        )

    if side == "LONG" and regime == "UP":
        return GuardianResult(
            passed=True,
            multiplier=1.0,
            reason="Trend-aligned LONG (legacy)",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT",
            setup_mode=SetupMode.CONTINUATION,
        )
    if side == "SHORT" and regime == "DOWN":
        return GuardianResult(
            passed=True,
            multiplier=1.0,
            reason="Trend-aligned SHORT (legacy)",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT",
            setup_mode=SetupMode.CONTINUATION,
        )

    return GuardianResult(
        passed=False,
        multiplier=0.0,
        reason="Counter-trend reversion (legacy)",
        metrics=metrics,
        gate_name="REGIME_ALIGNMENT",
    )
