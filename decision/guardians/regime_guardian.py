import logging

from .guardian_result import GuardianResult, SetupMode

logger = logging.getLogger("RegimeGuardian")

# V4 Regime: Value Position via Volume Profile (POC/VAH/VAL)
# No longer uses VWAP Z-score for value_position.
# VWAP Z is lagging; Volume Profile reflects actual auction consensus.
VA_EXCESS_FACTOR = 0.5  # Price beyond VAH/VAL + 50% of VA width = EXCESS


def check_regime_alignment(symbol: str, side: str, reversal_signal: dict, context_registry) -> GuardianResult:
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
    if not context_registry:
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

    # V4: Determine Value Position from Volume Profile (POC/VAH/VAL)
    # Volume Profile reflects where the auction actually formed consensus.
    # VWAP Z is lagging and assumes gaussian symmetry; VA is empirical.
    price = reversal_signal.get("close", 0.0) or reversal_signal.get("price", 0.0)
    poc, vah, val = 0.0, 0.0, 0.0
    if context_registry:
        poc, vah, val = context_registry.get_structural(symbol)

    # Fallback: if Volume Profile not ready, use VWAP Z (legacy)
    vwap_z_score = 0.0
    if poc == 0.0 and price > 0 and context_registry:
        vwap_z_score = context_registry.get_vwap_zscore(symbol, price)
        if vwap_z_score == 0.0:
            vwap_z_score = reversal_signal.get("z_score", 0.0)
        abs_z = abs(vwap_z_score)
        if abs_z >= 3.0:
            value_position = "EXCESS"
        elif abs_z >= 2.0:
            value_position = "OUT_OF_VALUE"
        else:
            value_position = "IN_VALUE"
    elif poc > 0 and vah > val:
        va_width = vah - val
        if price <= val:
            # Below Value Area
            if price < val - (va_width * VA_EXCESS_FACTOR):
                value_position = "EXCESS"
            else:
                value_position = "OUT_OF_VALUE"
        elif price >= vah:
            # Above Value Area
            if price > vah + (va_width * VA_EXCESS_FACTOR):
                value_position = "EXCESS"
            else:
                value_position = "OUT_OF_VALUE"
        else:
            # Inside Value Area (between VAL and VAH)
            value_position = "IN_VALUE"
    else:
        # No structural data at all — allow with low confidence
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
        "poc": round(poc, 4),
        "vah": round(vah, 4),
        "val": round(val, 4),
        "footprint_z_score": reversal_signal.get("z_score", 0.0),
        "side": side,
        "layers": {k: v.get("vote") if isinstance(v, dict) else v for k, v in layers.items()},
    }

    # =========================================================================
    # DECISION MATRIX: Value Position × Value Acceptance
    # =========================================================================

    # Phase 10.3 Restructuring: Toxic Flow Hard-Block
    # Pure reversion setups like TacticalAbsorptionV2 and Failed Breakout fail catastrophically
    # when attempting to catch falling knives or top-tick breakouts during price discovery.
    # If price is OUT_OF_VALUE or EXCESS, and the setup is pure reversion, BLOCK IT.
    tactical_type = reversal_signal.get("tactical_type", reversal_signal.get("setup_type", ""))
    is_pure_reversion = tactical_type in ("TacticalAbsorptionV2", "failed_breakout")

    if is_pure_reversion and value_position in ("OUT_OF_VALUE", "EXCESS"):
        return GuardianResult(
            passed=False,
            score=0.0,
            reason=f"BLOCKED (TOXIC FLOW) | {tactical_type} is structurally banned in {value_position}",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT_V3",
        )

    # --- BALANCE: Reversion is the natural trade, but edge depends on value_position
    if regime_v2 == "BALANCE":
        # BALANCE + OUT_OF_VALUE: Price outside Value Area → strong reversion edge
        if value_position in ("OUT_OF_VALUE", "EXCESS"):
            return GuardianResult(
                passed=True,
                score=1.0,
                reason=f"BALANCE | price@{price:.2f} ({value_position}, VA={val:.2f}-{vah:.2f}) → REVERSION",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.REVERSION,
            )
        # BALANCE + IN_VALUE: Price inside Value Area → ROTATION (not reversion)
        # AMT: In balance, price rotates VAL↔VAH. Reversion to POC is too close,
        # but rotation to opposite VA boundary IS a valid continuation trade.
        # LONG near VAL → target VAH, SHORT near VAH → target VAL.
        # Exception: Pure reversion strategies fade the micro-level and should be treated as REVERSION.
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

    # --- TREND: Price OUT_OF_VALUE → check Value Acceptance
    if regime_v2 in ("TREND_UP", "TREND_DOWN"):

        # Case 1: TREND + trend-aligned side + ACCEPTING → CONTINUATION
        # Market is accepting new prices, ride the trend on pullbacks
        if is_trend_aligned and value_acceptance == "ACCEPTING":
            return GuardianResult(
                passed=True,
                score=1.0,
                reason=f"IMBALANCE | {regime_v2} dir={direction} side={side} ({value_position}) → CONTINUATION",
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
                reason=f"IMBALANCE (weak) | {regime_v2} dir={direction} side={side} ({value_position}) → CONTINUATION",
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
                reason=f"EXCESS (weak) | {regime_v2} absorption outside VA → REVERSION",
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
                reason=f"IMBALANCE (absorption) | {regime_v2} ({value_position}) → CONTINUATION (pullback entry)",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V3",
                setup_mode=SetupMode.CONTINUATION,
            )

    # Fallback: BALANCE (should not reach here)
    return GuardianResult(
        passed=True,
        score=0.5,
        reason=f"DEFAULT BALANCE | regime={regime_v2} dir={direction} ({value_position})",
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
