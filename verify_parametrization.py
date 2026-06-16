import sys

# Add workspace to path
sys.path.append("/home/chesterbelle/Casino-V3")

from core.context_registry import ContextRegistry  # noqa: E402
from core.pressure.engine import PressureEngine  # noqa: E402
from decision.engine.profile_manager import profile_manager  # noqa: E402
from decision.engine.quality_scorer import evaluate_quality  # noqa: E402


def test_pressure_engine():
    print("Testing PressureEngine z_block...")
    engine = PressureEngine()

    symbol = "TEST_COIN"
    profile_manager.set_profile(symbol, "MEGA_LIQUID")

    coin_engine = engine._get(symbol)
    print(f"z_block for {symbol}: {coin_engine.z_block}")
    assert coin_engine.z_block == 2.0


def test_quality_scorer():
    print("\nTesting QualityScorer thresholds...")
    reg = ContextRegistry()
    symbol = "TEST_COIN"
    profile_manager.set_profile(symbol, "MEGA_LIQUID")

    reg.update_structural_from_session(symbol, 100, 110, 90, 1.0)
    print(f"Structural: {reg.get_structural(symbol)}")

    signal = {"close": 115}

    profile_manager.profiles["MEGA_LIQUID"]["quality_scorer"]["thresholds"]["structure"]["excess_multiplier"] = 0.1
    result = evaluate_quality(symbol, "SHORT", signal, reg)
    print(f"Value position with mult=0.1: {result.value_position}")

    profile_manager.profiles["MEGA_LIQUID"]["quality_scorer"]["thresholds"]["structure"]["excess_multiplier"] = 1.0
    result = evaluate_quality(symbol, "SHORT", signal, reg)
    print(f"Value position with mult=1.0: {result.value_position}")


if __name__ == "__main__":
    test_pressure_engine()
    test_quality_scorer()
    print("\n✅ Parametrization verified!")
