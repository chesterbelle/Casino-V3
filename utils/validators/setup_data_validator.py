"""
Setup Data Validator V4 (Layer 1.3)
-----------------------------------
Validates that SetupEngineV4 produces correct TP/SL prices based on
the new Crystal Layer V3.4c logic (ATR-relative and VWAP-based targets).
"""

import asyncio
import logging
import os
import sys
from typing import Tuple

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from decision.guardians.guardian_result import SetupMode
from decision.setup_engine import SetupEngineV4

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("SetupDataValidator")


class MockContextRegistry:
    def __init__(self, vwap=0.0, std=0.0, atr=0.0):
        self.vwap_state = {"BTCUSDT": {"vwap": vwap, "std": std}}
        self.atrs = {"BTCUSDT": {"short": atr}}

    def _norm_key(self, symbol):
        return symbol.replace("/", "").replace(":USDT", "")


def run_tests() -> bool:
    logger.info("=" * 60)
    logger.info("SETUP DATA VALIDATOR V4 (Layer 1.3)")
    logger.info("Validating ATR-Relative & VWAP-Based Targets")
    logger.info("=" * 60)
    all_passed = True
    symbol = "BTCUSDT"

    # We need a dummy engine for SetupEngineV4 init
    class DummyEngine:
        def subscribe(self, *args):
            pass

    setup_engine = SetupEngineV4(DummyEngine())

    # --- TEST 1: IN_VALUE Rotation (ATR-Relative) ---
    logger.info("\n--- Test 1: IN_VALUE Rotation (ATR-Relative) ---")
    # Entry at 60500, VWAP at 60000, STD 1000 (Z=0.5), ATR 500
    # Expected: SL = 60500 - 500 = 60000
    # Expected: TP = max(60500 + 500, VAH) -> VAH = 60000 + 1000 = 61000. TP = 61000
    context = MockContextRegistry(vwap=60000, std=1000, atr=500)
    setup_engine.context_registry = context

    tp, sl, mode, ref = setup_engine._calculate_targets(symbol, "LONG", 60500, SetupMode.CONTINUATION, "IN_VALUE")

    if tp == 61000 and sl == 60000 and mode == "rotation":
        logger.info(f"✅ Passed: TP={tp}, SL={sl}, Mode={mode}")
    else:
        logger.error(f"❌ Failed: Expected TP 61000, SL 60000, Mode rotation. Got TP={tp}, SL={sl}, Mode={mode}")
        all_passed = False

    # --- TEST 2: OUT_OF_VALUE Reversion (VWAP Target) ---
    logger.info("\n--- Test 2: OUT_OF_VALUE Reversion (VWAP Target) ---")
    # Entry at 62000, VWAP at 60000, STD 1000 (Z=2.0), ATR 500
    # Expected: TP = VWAP = 60000
    # Expected: SL = VWAP + 3.5*STD = 60000 + 3500 = 63500
    context = MockContextRegistry(vwap=60000, std=1000, atr=500)
    setup_engine.context_registry = context

    tp, sl, mode, ref = setup_engine._calculate_targets(symbol, "SHORT", 62000, SetupMode.REVERSION, "OUT_OF_VALUE")

    if tp == 60000 and sl == 63500 and mode == "reversion":
        logger.info(f"✅ Passed: TP={tp}, SL={sl}, Mode={mode}")
    else:
        logger.error(f"❌ Failed: Expected TP 60000, SL 63500, Mode reversion. Got TP={tp}, SL={sl}, Mode={mode}")
        all_passed = False

    # --- TEST 3: OUT_OF_VALUE Continuation (Trend Extension) ---
    logger.info("\n--- Test 3: OUT_OF_VALUE Continuation (Trend Extension) ---")
    # Entry at 62000, VWAP at 60000, STD 1000 (Z=2.0), ATR 500
    # Expected: TP = Entry + 1.5*ATR = 62000 + 750 = 62750
    # Expected: SL = VWAP = 60000
    context = MockContextRegistry(vwap=60000, std=1000, atr=500)
    setup_engine.context_registry = context

    tp, sl, mode, ref = setup_engine._calculate_targets(symbol, "LONG", 62000, SetupMode.CONTINUATION, "OUT_OF_VALUE")

    if tp == 62750 and sl == 60000 and mode == "continuation":
        logger.info(f"✅ Passed: TP={tp}, SL={sl}, Mode={mode}")
    else:
        logger.error(f"❌ Failed: Expected TP 62750, SL 60000, Mode continuation. Got TP={tp}, SL={sl}, Mode={mode}")
        all_passed = False

    # --- TEST 4: Fee Safety Guard (Min 0.20% TP) ---
    logger.info("\n--- Test 4: Fee Safety Guard (Min 0.20% TP) ---")
    # Entry at 60050, VWAP at 60000. TP is too close (0.08%).
    # Expected: TP forced to 0.25% distance -> 60050 * 1.0025 = 60200.125
    context = MockContextRegistry(vwap=60000, std=1000, atr=500)
    setup_engine.context_registry = context

    tp, sl, mode, ref = setup_engine._calculate_targets(symbol, "LONG", 60050, SetupMode.REVERSION, "IN_VALUE")

    if tp > 60200:
        logger.info(f"✅ Passed: TP={tp} (Forced extension active)")
    else:
        logger.error(f"❌ Failed: TP={tp} was not extended despite being too close to entry.")
        all_passed = False

    return all_passed


if __name__ == "__main__":
    if run_tests():
        logger.info("\n✅ ALL SETUP DATA TESTS PASSED")
        sys.exit(0)
    else:
        logger.error("\n❌ SOME SETUP DATA TESTS FAILED")
        sys.exit(1)
