import logging

import config.strategies as strat_config

from .guardian_result import GuardianResult, SetupMode

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
            score = 1.0 if confidence < 0.6 else 0.7
            return GuardianResult(
                passed=True,
                score=score,
                reason=f"Local consensus (Micro/Meso Neutral) overrides Macro {regime_v2}",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
            )

        if regime_v2 == "BALANCE":
            return GuardianResult(
                passed=True,
                score=1.0,
                reason="Balance regime",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
                setup_mode=SetupMode.REVERSION,
            )

        # Confidence based logic for Trends
        if regime_v2 == "TREND_UP":
            if side == "SHORT":
                if confidence > 0.3:
                    return GuardianResult(
                        passed=False,
                        score=0.0,
                        reason="Strong TREND_UP",
                        metrics=metrics,
                        gate_name="REGIME_ALIGNMENT_V2",
                    )
                score = max(0.1, 1.0 - confidence)
                return GuardianResult(
                    passed=True,
                    score=score,
                    reason="Counter-trend (TREND_UP)",
                    metrics=metrics,
                    gate_name="REGIME_ALIGNMENT_V2",
                    setup_mode=SetupMode.REVERSION,
                )
            else:
                mode = SetupMode.CONTINUATION if confidence > 0.25 else SetupMode.REVERSION
                return GuardianResult(
                    passed=True,
                    score=1.0,
                    reason="Trend-aligned (UP)",
                    metrics=metrics,
                    gate_name="REGIME_ALIGNMENT_V2",
                    setup_mode=mode,
                )

        if regime_v2 == "TREND_DOWN":
            if side == "LONG":
                if confidence > 0.3:
                    return GuardianResult(
                        passed=False,
                        score=0.0,
                        reason="Strong TREND_DOWN",
                        metrics=metrics,
                        gate_name="REGIME_ALIGNMENT_V2",
                    )
                score = max(0.1, 1.0 - confidence)
                return GuardianResult(
                    passed=True,
                    score=score,
                    reason="Counter-trend (TREND_DOWN)",
                    metrics=metrics,
                    gate_name="REGIME_ALIGNMENT_V2",
                    setup_mode=SetupMode.REVERSION,
                )
            else:
                mode = SetupMode.CONTINUATION if confidence > 0.25 else SetupMode.REVERSION
                return GuardianResult(
                    passed=True,
                    score=1.0,
                    reason="Trend-aligned (DOWN)",
                    metrics=metrics,
                    gate_name="REGIME_ALIGNMENT_V2",
                    setup_mode=mode,
                )

        if regime_v2 == "TRANSITION":
            z_score = abs(reversal_signal.get("z_score", 0.0))
            if z_score >= strat_config.LTA_TRANSITION_Z_THRESHOLD:
                return GuardianResult(
                    passed=True,
                    score=0.5,
                    reason="Transition Recovery (Extreme Flow)",
                    metrics=metrics,
                    gate_name="REGIME_ALIGNMENT_V2",
                    setup_mode=SetupMode.REVERSION,
                )
            return GuardianResult(
                passed=False,
                score=0.0,
                reason=f"TRANSITION state (dir={direction}, conf={confidence:.2f})",
                metrics=metrics,
                gate_name="REGIME_ALIGNMENT_V2",
            )

    # Legacy fallback
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
