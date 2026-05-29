"""
Quality Scoring Engine — v8.4 Crystal Reforge

Replaces the rigid guardian kill-chain with a graduated quality score.
Each factor contributes 0.0-1.0, weighted by importance.
Final score maps to grade A/B/None for AdaptivePlayer sizing.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from core.footprint_registry import footprint_registry
from decision.engine.profile_manager import profile_manager
from decision.guardians.guardian_result import SetupMode

logger = logging.getLogger("QualityScorer")

# Default weights (used if no profile loaded)
DEFAULT_WEIGHTS = {
    "exhaustion": 0.35,
    "regime": 0.25,
    "structure": 0.20,
    "liquidity": 0.15,
    "spread": 0.05,
}

# Default grade thresholds
DEFAULT_GRADE_A = 0.7
DEFAULT_GRADE_B = 0.4

# Hard blocks (only truly dangerous situations)
SPREAD_HARD_BLOCK = 3.0  # 3x average spread = block


@dataclass
class QualityResult:
    """Result of quality scoring."""

    quality_score: float  # 0.0-1.0
    grade: Optional[str]  # "A", "B", or None
    setup_mode: SetupMode
    value_position: str
    scores: Dict[str, float] = field(default_factory=dict)
    reasons: Dict[str, str] = field(default_factory=dict)
    passed: bool = True  # Only False for hard blocks
    block_reason: str = ""


def _score_exhaustion(symbol: str) -> Tuple[float, str]:
    """
    Score exhaustion using footprint metrics.
    Returns (score 0.0-1.0, reason string).
    """
    try:
        exhaustion = footprint_registry.get_exhaustion(symbol)
        if not exhaustion.get("ready", False):
            return 0.5, "Exhaustion data not ready (neutral)"

        delta_ratio = exhaustion.get("delta_ratio", 1.0)
        volume_ratio = exhaustion.get("volume_ratio", 1.0)

        if delta_ratio > 1.5:
            return 0.0, f"Agresor intensificándose (δ={delta_ratio:.2f})"
        elif delta_ratio < 0.5:
            score = 1.0
            if volume_ratio < 0.4:
                score = min(score + 0.1, 1.0)  # Bonus for volume drop
            return score, f"Agotamiento perfecto (δ={delta_ratio:.2f}, v={volume_ratio:.2f})"
        else:
            score = 1.0 - delta_ratio
            return score, f"Agotamiento parcial (δ={delta_ratio:.2f})"
    except Exception as e:
        logger.debug(f"Exhaustion scoring failed: {e}")
        return 0.5, f"Exhaustion error: {e}"


def _score_regime(symbol: str, side: str, signal: dict, context_registry) -> Tuple[float, str, SetupMode, str]:
    """
    Score regime alignment using existing regime guardian logic.
    Returns (score, reason, setup_mode, value_position).
    """
    from decision.guardians.regime_guardian import check_regime_alignment

    result = check_regime_alignment(symbol, side, signal, context_registry)

    # Convert guardian result to quality score
    if not result.passed:
        return 0.0, result.reason, SetupMode.NEUTRAL, "UNKNOWN"

    # Use guardian's score directly (already 0.0-1.0)
    score = result.score
    setup_mode = result.setup_mode
    value_position = result.metrics.get("value_position", "OUT_OF_VALUE") if result.metrics else "OUT_OF_VALUE"

    return score, result.reason, setup_mode, value_position


def _score_structure(
    symbol: str, price: float, side: str, setup_mode: SetupMode, context_registry
) -> Tuple[float, str]:
    """
    Score structure geography.
    Returns (score, reason).
    """
    from decision.guardians.structure_guardian import check_structure_alignment

    result = check_structure_alignment(symbol, price, side, setup_mode, context_registry)

    if not result.passed:
        return 0.0, result.reason

    return result.score, result.reason


def _score_liquidity(symbol: str, side: str, target_price: float, context_registry) -> Tuple[float, str]:
    """
    Score liquidity using L2 ratio.
    Returns (score, reason).
    """
    if not context_registry:
        return 0.5, "No context registry"

    l2_ratio = context_registry.get_l2_ratio(symbol, side)
    if l2_ratio is None:
        return 0.5, "No L2 data"

    # Graduated scoring instead of hard block
    if l2_ratio >= 2.0:
        return 1.0, f"Strong wall (L2={l2_ratio:.2f})"
    elif l2_ratio >= 1.5:
        return 0.7, f"Adequate wall (L2={l2_ratio:.2f})"
    elif l2_ratio >= 1.0:
        return 0.4, f"Weak wall (L2={l2_ratio:.2f})"
    else:
        return 0.1, f"Very thin wall (L2={l2_ratio:.2f})"


def _score_spread(symbol: str, context_registry) -> Tuple[float, str, bool]:
    """
    Score spread. Returns (score, reason, is_hard_block).
    """
    # Spread scoring not yet implemented - return neutral
    return 1.0, "Spread scoring not implemented", False


def evaluate_quality(
    symbol: str,
    side: str,
    signal: dict,
    context_registry,
    trace=None,
) -> QualityResult:
    """
    Main entry point: evaluate signal quality across all factors.
    Returns QualityResult with score, grade, and metadata.
    """
    price = signal.get("close", 0.0) or signal.get("price", 0.0)

    # 1. Exhaustion score (the core)
    exhaustion_score, exhaustion_reason = _score_exhaustion(symbol)

    # 2. Regime score
    regime_score, regime_reason, setup_mode, value_position = _score_regime(symbol, side, signal, context_registry)

    # 3. Structure score
    structure_score, structure_reason = _score_structure(symbol, price, side, setup_mode, context_registry)

    # 4. Liquidity score
    liquidity_score, liquidity_reason = _score_liquidity(symbol, side, price, context_registry)

    # 5. Spread score (with hard block check)
    spread_score, spread_reason, spread_hard_block = _score_spread(symbol, context_registry)

    # Hard block: spread > 3x
    if spread_hard_block:
        return QualityResult(
            quality_score=0.0,
            grade=None,
            setup_mode=setup_mode,
            value_position=value_position,
            scores={"spread": 0.0},
            reasons={"spread": spread_reason},
            passed=False,
            block_reason=spread_reason,
        )

    # Get weights from profile or use defaults
    profile_params = profile_manager.get_quality_scorer_params(symbol)
    weights = profile_params.get("weights", DEFAULT_WEIGHTS)
    grade_a = profile_params.get("grade_thresholds", {}).get("A", DEFAULT_GRADE_A)
    grade_b = profile_params.get("grade_thresholds", {}).get("B", DEFAULT_GRADE_B)

    # Calculate weighted quality score
    quality_score = (
        exhaustion_score * weights.get("exhaustion", 0.35)
        + regime_score * weights.get("regime", 0.25)
        + structure_score * weights.get("structure", 0.20)
        + liquidity_score * weights.get("liquidity", 0.15)
        + spread_score * weights.get("spread", 0.05)
    )

    # Map to grade
    if quality_score >= grade_a:
        grade = "A"
    elif quality_score >= grade_b:
        grade = "B"
    else:
        grade = None

    # Build result
    result = QualityResult(
        quality_score=round(quality_score, 3),
        grade=grade,
        setup_mode=setup_mode,
        value_position=value_position,
        scores={
            "exhaustion": round(exhaustion_score, 3),
            "regime": round(regime_score, 3),
            "structure": round(structure_score, 3),
            "liquidity": round(liquidity_score, 3),
            "spread": round(spread_score, 3),
        },
        reasons={
            "exhaustion": exhaustion_reason,
            "regime": regime_reason,
            "structure": structure_reason,
            "liquidity": liquidity_reason,
            "spread": spread_reason,
        },
        passed=True,
    )

    # Trace logging
    if trace:
        trace.add_step(
            "QualityScorer",
            grade is not None,
            f"Quality={quality_score:.3f} Grade={grade or 'NONE'}",
            {
                "quality_score": quality_score,
                "grade": grade,
                "exhaustion": exhaustion_score,
                "regime": regime_score,
                "structure": structure_score,
                "liquidity": liquidity_score,
                "spread": spread_score,
            },
        )

    logger.info(
        f"📊 [QUALITY] {symbol} {side} | Score={quality_score:.3f} Grade={grade or 'NONE'} | "
        f"E={exhaustion_score:.2f} R={regime_score:.2f} S={structure_score:.2f} "
        f"L={liquidity_score:.2f} Sp={spread_score:.2f}"
    )

    return result
