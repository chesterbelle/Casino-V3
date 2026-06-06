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


def _score_exhaustion(symbol: str, thresholds: Dict) -> Tuple[float, str]:
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

        # Parametric thresholds
        block_thresh = thresholds.get("block", 1.5)
        perfect_thresh = thresholds.get("perfect", 0.5)
        vol_bonus_thresh = thresholds.get("vol_bonus", 0.4)

        if delta_ratio > block_thresh:
            return 0.0, f"Agresor intensificándose (δ={delta_ratio:.2f})"
        elif delta_ratio < perfect_thresh:
            score = 1.0
            if volume_ratio < vol_bonus_thresh:
                score = min(score + 0.1, 1.0)  # Bonus for volume drop
            return score, f"Agotamiento perfecto (δ={delta_ratio:.2f}, v={volume_ratio:.2f})"
        else:
            score = 1.0 - delta_ratio
            return score, f"Agotamiento parcial (δ={delta_ratio:.2f})"
    except Exception as e:
        logger.debug(f"Exhaustion scoring failed: {e}")
        return 0.5, f"Exhaustion error: {e}"


def _score_regime(
    symbol: str, side: str, signal: dict, context_registry, thresholds: Dict
) -> Tuple[float, str, SetupMode, str]:
    """
    Score regime/cascade alignment using PressureState from ContextRegistry.
    Returns (score, reason, setup_mode, value_position).
    """
    if not context_registry:
        return 1.0, "No context registry", SetupMode.REVERSION, "IN_VALUE"

    state = context_registry.get_pressure_state(symbol)
    if not state:
        return 1.0, "No pressure state available (neutral)", SetupMode.REVERSION, "IN_VALUE"

    # Anti-cascade check: if we are trying to go counter-trend in a cascade, fail it.
    if side == "LONG" and state.block_long:
        return 0.0, f"BLOCKED | Price cascading down (Z={state.price_displacement_z:.2f})", SetupMode.NEUTRAL, "EXCESS"
    if side == "SHORT" and state.block_short:
        return 0.0, f"BLOCKED | Price cascading up (Z={state.price_displacement_z:.2f})", SetupMode.NEUTRAL, "EXCESS"

    # Check value position from Volume Profile levels
    price = signal.get("close", 0.0) or signal.get("price", 0.0)
    poc, vah, val = context_registry.get_structural(symbol) if context_registry else (0.0, 0.0, 0.0)

    value_position = "IN_VALUE"
    if poc > 0 and vah > val:
        va_width = vah - val
        excess_mult = thresholds.get("excess_multiplier", 0.5)
        if price <= val:
            value_position = "EXCESS" if price < val - (va_width * excess_mult) else "OUT_OF_VALUE"
        elif price >= vah:
            value_position = "EXCESS" if price > vah + (va_width * excess_mult) else "OUT_OF_VALUE"

    # For zero-state, all setups default to SetupMode.REVERSION
    return 1.0, "Aligned", SetupMode.REVERSION, value_position


def _score_structure(
    symbol: str, price: float, side: str, setup_mode: SetupMode, context_registry
) -> Tuple[float, str]:
    """
    Score structure proximity.
    """
    if not context_registry:
        return 1.0, "No registry"
    poc, vah, val = context_registry.get_structural(symbol)
    if poc == 0.0:
        return 0.5, "No structural levels loaded (neutral)"
    return 1.0, "Structural levels loaded"


def _score_liquidity(
    symbol: str, side: str, target_price: float, context_registry, thresholds: Dict
) -> Tuple[float, str]:
    """
    Score liquidity using L2 ratio.
    Returns (score, reason).
    """
    if not context_registry:
        return 0.5, "No context registry"

    l2_ratio = context_registry.get_l2_ratio(symbol, side)
    if l2_ratio is None:
        return 0.5, "No L2 data"

    # Parametric scoring
    strong_t = thresholds.get("strong", 2.0)
    adequate_t = thresholds.get("adequate", 1.5)
    weak_t = thresholds.get("weak", 1.0)

    if l2_ratio >= strong_t:
        return 1.0, f"Strong wall (L2={l2_ratio:.2f})"
    elif l2_ratio >= adequate_t:
        return 0.7, f"Adequate wall (L2={l2_ratio:.2f})"
    elif l2_ratio >= weak_t:
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

    # Get weights and thresholds from profile or use defaults
    profile_params = profile_manager.get_quality_scorer_params(symbol)
    weights = profile_params.get("weights", DEFAULT_WEIGHTS)
    grade_a = profile_params.get("grade_thresholds", {}).get("A", DEFAULT_GRADE_A)
    grade_b = profile_params.get("grade_thresholds", {}).get("B", DEFAULT_GRADE_B)
    thresholds = profile_params.get(
        "thresholds",
        {
            "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
            "liquidity": {"strong": 2.0, "adequate": 1.5, "weak": 1.0},
            "structure": {"excess_multiplier": 0.5},
        },
    )

    # 1. Exhaustion score (the core)
    exhaustion_score, exhaustion_reason = _score_exhaustion(symbol, thresholds)

    # 2. Regime score
    regime_score, regime_reason, setup_mode, value_position = _score_regime(
        symbol, side, signal, context_registry, thresholds
    )

    # 3. Structure score
    structure_score, structure_reason = _score_structure(symbol, price, side, setup_mode, context_registry)

    # 4. Liquidity score
    liquidity_score, liquidity_reason = _score_liquidity(symbol, side, price, context_registry, thresholds)

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

    # Structural counter-trend penalty: if regime guardian blocked the signal
    # (regime_score == 0.0), require A-grade minimum. Counter-trend entries
    # need near-perfect exhaustion + structure + liquidity to pass.
    if regime_score == 0.0 and grade != "A":
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
