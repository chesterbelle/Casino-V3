import sys

sys.path.append("/home/chesterbelle/Casino-V3")

from unittest.mock import MagicMock

from core.context_registry import ContextRegistry
from decision.engine.profile_manager import profile_manager
from decision.engine.quality_scorer import evaluate_quality


def test_quality_filtering():
    print("Testing QualityScorer filtering...")
    reg = ContextRegistry()

    # Setup a symbol in THIN_VOLATILE
    symbol = "THIN_COIN"
    profile_manager.set_profile(symbol, "THIN_VOLATILE")

    # Thresholds for THIN_VOLATILE: A=0.85, B=0.60
    # Weights: {exhaustion: 0.40, regime: 0.20, structure: 0.20, liquidity: 0.15, spread: 0.05}

    # Case 1: Low score (should be grade None and passed=False)
    # Exhaustion=0.1, Regime=0.1, Structure=0.1, Liquidity=0.1, Spread=0.1
    # Score = 0.1 * (0.4+0.2+0.2+0.15+0.05) = 0.1

    # Mock registries to return low scores
    # We need to mock the inner functions or the registry
    # For simplicity, we can mock the registry methods that _score_* functions call.

    reg.get_pressure_state = MagicMock(
        return_value=MagicMock(block_long=False, block_short=False, price_displacement_z=0.0)
    )
    reg.get_structural = MagicMock(return_value=(100, 110, 90))
    reg.get_l2_ratio = MagicMock(return_value=0.1)  # Very thin

    # Mock footprint_registry since it's a global
    import core.footprint_registry

    core.footprint_registry.footprint_registry.get_exhaustion = MagicMock(
        return_value={"ready": True, "delta_ratio": 1.4, "volume_ratio": 1.0}
    )
    # delta_ratio 1.4 is between perfect (0.3) and block (1.2)? No, for THIN_VOLATILE block is 1.2.
    # So 1.4 should return score 0.0.

    signal = {"close": 100}
    result = evaluate_quality(symbol, "LONG", signal, reg)

    print(f"Low score result: Score={result.quality_score}, Grade={result.grade}, Passed={result.passed}")
    assert result.grade is None
    assert result.passed is False

    # Case 2: High score (should be Grade A/B and passed=True)
    core.footprint_registry.footprint_registry.get_exhaustion = MagicMock(
        return_value={"ready": True, "delta_ratio": 0.1, "volume_ratio": 0.1}
    )
    # delta_ratio 0.1 < perfect 0.3 -> score 1.1 (with bonus)

    reg.get_l2_ratio = MagicMock(return_value=4.0)  # Strong wall

    result = evaluate_quality(symbol, "LONG", signal, reg)
    print(f"High score result: Score={result.quality_score}, Grade={result.grade}, Passed={result.passed}")
    assert result.grade in ["A", "B"]
    assert result.passed is True

    print("\n✅ QualityScorer filtering verified!")


if __name__ == "__main__":
    test_quality_filtering()
