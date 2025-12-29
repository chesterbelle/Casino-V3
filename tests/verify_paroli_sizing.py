import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from config import trading
from players import paroli_player


def test_paroli_sizing():
    print("Testing Paroli Player Sizing Logic...")

    # Mock config values if needed, but we'll use the imported ones first
    print(f"Config MAX_POSITION_SIZE: {trading.MAX_POSITION_SIZE}")
    print(f"Paroli BASE_DIVISOR: {paroli_player.BASE_DIVISOR}")

    # Scenario 1: Standard case
    equity = 10000.0

    # Initialize state
    state = paroli_player.init_state()

    # Prepare state (calculates unit)
    state, meta = paroli_player.prepare_state(state, equity)
    print(f"\nInitial Unit: {state['unit']} (Should be {equity/100})")

    # Mock Verdict
    class MockVerdict:
        side = "LONG"

    verdict = MockVerdict()

    # Step 0 (1x)
    size_fraction = paroli_player.calculate_position_size(verdict, equity, meta)
    print(f"Step 0 (1x) Fraction: {size_fraction:.4f} (Expected ~0.01)")

    # Advance to Step 1 (4x)
    state["step"] = 1
    meta["paroli_state"] = state
    size_fraction = paroli_player.calculate_position_size(verdict, equity, meta)
    print(f"Step 1 (4x) Fraction: {size_fraction:.4f} (Expected ~0.04)")

    # Advance to Step 2 (8x)
    state["step"] = 2
    meta["paroli_state"] = state
    size_fraction = paroli_player.calculate_position_size(verdict, equity, meta)
    print(f"Step 2 (8x) Fraction: {size_fraction:.4f} (Expected ~0.08)")

    if size_fraction > trading.MAX_POSITION_SIZE:
        print(f"❌ FAILURE: Step 2 size {size_fraction} exceeds max {trading.MAX_POSITION_SIZE}")
    else:
        print(f"✅ SUCCESS: Step 2 size {size_fraction} respects max {trading.MAX_POSITION_SIZE}")

    # Scenario 2: Constrained case (Low MAX_POSITION_SIZE)
    print("\n--- Scenario 2: Low MAX_POSITION_SIZE (0.05) ---")
    # Temporarily patch the MAX_POSITION_SIZE in the table_meta to simulate a constraint
    # The player uses table_meta.get("max_position_fraction") or config

    meta["table"] = {"max_position_fraction": 0.05}

    # Reset state
    state = paroli_player.init_state()
    state, meta_low = paroli_player.prepare_state(state, equity)
    meta_low["table"] = {"max_position_fraction": 0.05}

    # The unit should be adjusted down because 8x unit would be 0.08 which is > 0.05
    # Max unit allowed = (10000 * 0.05) / 8 = 62.5
    # Default unit = 100
    # So unit should become 62.5

    # We need to call calculate_position_size to trigger the unit adjustment logic
    # It happens inside calculate_position_size

    # Check Step 2 (8x) directly to see if it adjusted
    state["step"] = 2
    meta_low["paroli_state"] = state

    size_fraction = paroli_player.calculate_position_size(verdict, equity, meta_low)
    print(f"Step 2 (8x) Fraction with limit 0.05: {size_fraction:.4f}")

    if size_fraction > 0.05001:  # float tolerance
        print(f"❌ FAILURE: Size {size_fraction} exceeds limit 0.05")
    else:
        print(f"✅ SUCCESS: Size {size_fraction} respects limit 0.05")

    print(f"Adjusted Unit in State: {state['unit']} (Expected 62.5)")


if __name__ == "__main__":
    test_paroli_sizing()
