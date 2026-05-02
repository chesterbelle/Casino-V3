import logging

import config.strategies as strat_config

from .guardian_result import GuardianResult

logger = logging.getLogger("RegimeGuardian")


def check_regime_alignment(
    symbol: str, side: str, reversal_signal: dict, context_registry, fast_track: bool
) -> GuardianResult:
    if fast_track or not context_registry:
        return GuardianResult(passed=True, multiplier=1.0, gate_name="REGIME_ALIGNMENT")

    # Phase 2100: Try V2 regime first
    regime_v2_data = getattr(context_registry, "_regime_v2", {}).get(symbol)
    if regime_v2_data:
        regime_v2 = regime_v2_data.get("regime", "BALANCE")
        direction = regime_v2_data.get("direction", "NEUTRAL")
        confidence = regime_v2_data.get("confidence", 0.0)
        layers = regime_v2_data.get("layers", {})

        metrics = {
            "regime_v2": regime_v2,
            "direction": direction,
            "confidence": confidence,
            "side": side,
            "layers": {k: v.get("vote") for k, v in layers.items()},
        }

        micro_vote = (
            layers.get("micro", {}).get("vote", "NEUTRAL")
            if isinstance(layers.get("micro"), dict)
            else layers.get("micro", "NEUTRAL")
        )
        meso_vote = (
            layers.get("meso", {}).get("vote", "NEUTRAL")
            if isinstance(layers.get("meso"), dict)
            else layers.get("meso", "NEUTRAL")
        )

        if micro_vote == "NEUTRAL" and meso_vote == "NEUTRAL":
            local_mult = 1.0 if confidence < 0.6 else strat_config.LTA_SOFT_GATE_REDUCTION
            return GuardianResult(
                passed=True,
                multiplier=local_mult,
                reason=f"Local consensus (Micro/Meso Neutral) overrides Macro {regime_v2}",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
            )

        if confidence < 0.5:
            return GuardianResult(
                passed=True,
                multiplier=strat_config.LTA_SOFT_GATE_REDUCTION,
                reason=f"Low confidence ({confidence:.2f}) - counter-trend allowed",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
            )

        if regime_v2 == "BALANCE":
            return GuardianResult(
                passed=True, multiplier=1.0, reason="Balance regime", metrics=metrics, gate_name="REGIME_ALIGNMENT_V2"
            )

        if regime_v2 == "TRANSITION":
            z_score = abs(reversal_signal.get("z_score", 0.0))
            if z_score >= strat_config.LTA_TRANSITION_Z_THRESHOLD:
                logger.info(
                    f"🛡️ [REGIME_V2] {symbol} {side} RECOVERED in TRANSITION: Extreme Z-Score {z_score:.2f} >= {strat_config.LTA_TRANSITION_Z_THRESHOLD}"
                )
                return GuardianResult(
                    passed=True,
                    multiplier=strat_config.LTA_SOFT_GATE_REDUCTION,
                    reason="Transition Recovery (Extreme Flow)",
                    metrics=metrics,
                    gate_name="REGIME_ALIGNMENT_V2",
                )

            logger.info(
                f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TRANSITION state (conf={confidence:.2f}, dir={direction}) — market leaving balance"
            )
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason=f"TRANSITION state (dir={direction}, conf={confidence:.2f})",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
            )

        if regime_v2 == "TREND_UP":
            logger.info(
                f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TREND_UP active (conf={confidence:.2f}) — mean-reversion disabled"
            )
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason=f"TREND_UP - mean-reversion disabled (conf={confidence:.2f})",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
            )

        if regime_v2 == "TREND_DOWN":
            logger.info(
                f"🛡️ [REGIME_V2] {symbol} {side} BLOCKED: TREND_DOWN active (conf={confidence:.2f}) — mean-reversion disabled"
            )
            return GuardianResult(
                passed=False,
                multiplier=0.0,
                reason=f"TREND_DOWN - mean-reversion disabled (conf={confidence:.2f})",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
            )

    # Legacy fallback: OTF-based regime
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
        )
    if side == "SHORT" and regime == "DOWN":
        return GuardianResult(
            passed=True,
            multiplier=1.0,
            reason="Trend-aligned SHORT (legacy)",
            metrics=metrics,
            gate_name="REGIME_ALIGNMENT",
        )

    logger.info(f"🛡️ [REGIME_OTF] {symbol} {side} blocked: Counter-trend (Regime: {regime}, OTF: {otf})")
    return GuardianResult(
        passed=False,
        multiplier=0.0,
        reason="Counter-trend reversion (legacy)",
        metrics=metrics,
        gate_name="REGIME_ALIGNMENT",
    )
