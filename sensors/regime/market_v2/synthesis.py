"""
Regime Sensor V2 — Synthesis Logic

Hierarchical Bayesian synthesis:
  Level 1: Price Action (lead detector) — declares trend direction
  Level 2: Volume Profile (confirmation) — confirms or vetoes
  Level 3: Markov (memory) — adjusts confidence based on historical transitions
"""

import logging

logger = logging.getLogger("RegimeSensorV2.Synthesis")


def synthesize(
    price_action: dict,
    volume_profile: dict,
    markov=None,
) -> dict:
    """
    Combine Price Action and Volume Profile into a regime verdict.

    Logic:
      1. If Price Action has no conviction → BALANCE
      2. Price Action has conviction → declare TREND direction
      3. Volume Profile confirms → confidence escalates
      4. Volume Profile vetoes → degrade to BALANCE
      5. Markov adjusts confidence if it agrees with direction

    Args:
        price_action: Output from _PriceActionLayer.evaluate()
        volume_profile: Output from _VolumeProfileLayer.evaluate()
        markov: Optional MarkovRegimeDetector instance

    Returns:
        {
            "regime": "BALANCE" | "TREND_UP" | "TREND_DOWN",
            "direction": "UP" | "DOWN" | "NEUTRAL",
            "confidence": float,
            "value_acceptance": str,
            "absorption_detected": bool,
        }
    """
    pa_vote = price_action.get("vote", "NEUTRAL")
    pa_score = price_action.get("score", 0.0)
    vp_vote = volume_profile.get("vote", "NEUTRAL")
    vp_score = volume_profile.get("score", 0.0)

    absorption_detected = volume_profile.get("absorption_detected", False)
    value_acceptance = volume_profile.get("value_acceptance", "NEUTRAL")

    # Level 1: Price Action leads
    # If Price Action has no conviction → BALANCE
    if pa_vote == "NEUTRAL" or pa_score < 0.3:
        return {
            "regime": "BALANCE",
            "direction": "NEUTRAL",
            "confidence": pa_score,
            "value_acceptance": "REJECTING" if absorption_detected else value_acceptance,
            "absorption_detected": absorption_detected,
        }

    # Price Action has conviction — declare TREND direction
    direction = pa_vote
    regime = f"TREND_{direction}"

    # Level 2: Volume Profile confirms or vetoes
    if vp_vote == direction and vp_score > 0.2:
        # Strong confirmation → confidence escalates
        confidence = max(pa_score, (pa_score + vp_score) / 2)
    elif vp_vote != "NEUTRAL" and vp_vote != direction and vp_score >= 0.3:
        # Strong veto → degrade to BALANCE
        return {
            "regime": "BALANCE",
            "direction": "NEUTRAL",
            "confidence": pa_score * 0.5,
            "value_acceptance": "REJECTING" if absorption_detected else value_acceptance,
            "absorption_detected": absorption_detected,
        }
    else:
        # No strong confirmation or veto → moderate confidence
        confidence = pa_score * 0.8

    # Level 3: Markov memory adjustment
    if markov and markov._trained:
        dominant = markov.get_dominant()
        markov_conf = markov.get_confidence()

        # If Markov agrees with direction, boost confidence
        if dominant == direction and markov_conf > 0.50:
            confidence *= 1.10
        # If Markov strongly disagrees, slightly reduce confidence
        elif dominant != direction and dominant != "BALANCE" and markov_conf > 0.55:
            confidence *= 0.85

    # Value acceptance
    if absorption_detected:
        value_acceptance = "REJECTING"
    elif vp_vote == direction and vp_score > 0:
        value_acceptance = "ACCEPTING"

    return {
        "regime": regime,
        "direction": direction,
        "confidence": round(min(1.0, confidence), 3),
        "value_acceptance": value_acceptance,
        "absorption_detected": absorption_detected,
    }
