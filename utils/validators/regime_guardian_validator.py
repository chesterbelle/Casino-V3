"""
Regime Guardian V3 Math Validator (Layer 0.H)
---------------------------------------------
Validates the 7-case decision matrix (Value Position x Value Acceptance).
"""

import asyncio
import logging
import os
import sys

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from decision.guardians.guardian_result import SetupMode
from decision.guardians.regime_guardian import check_regime_alignment

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("RegimeGuardianValidator")


class MockContextRegistry:
    def __init__(self, vwap_z_score=0.0, regime_v2_data=None, structural=(0.0, 0.0, 0.0)):
        self.vwap_z_score = vwap_z_score
        self._regime_v2 = {"BTC/USDT:USDT": regime_v2_data or {}}
        self._structural = structural  # (poc, vah, val)

    def get_vwap_zscore(self, symbol, price):
        return self.vwap_z_score

    def get_structural(self, symbol):
        """Return (poc, vah, val). Default (0,0,0) forces VWAP Z fallback."""
        return self._structural


def run_tests() -> bool:
    logger.info("=" * 60)
    logger.info("REGIME GUARDIAN V3 VALIDATION (Layer 0.H)")
    logger.info("=" * 60)
    all_passed = True
    symbol = "BTC/USDT:USDT"

    # Case 1: BALANCE + OUT_OF_VALUE -> REVERSION
    logger.info("\n--- Case 1: BALANCE + OUT_OF_VALUE -> REVERSION ---")
    regime_data = {"regime": "BALANCE", "direction": "NEUTRAL", "value_acceptance": "NEUTRAL", "confidence": 0.0}
    context = MockContextRegistry(vwap_z_score=2.5, regime_v2_data=regime_data)
    res = check_regime_alignment(symbol, "LONG", {"price": 60000}, context)
    if res.passed and res.setup_mode == SetupMode.REVERSION:
        logger.info("✅ Passed (Reversion)")
    else:
        logger.error(
            f"❌ Failed: expected passed=True, setup_mode=REVERSION, got passed={res.passed}, mode={res.setup_mode}"
        )
        all_passed = False

    # Case 2: BALANCE + IN_VALUE -> CONTINUATION (Rotation)
    logger.info("\n--- Case 2: BALANCE + IN_VALUE -> CONTINUATION (Rotation) ---")
    regime_data = {"regime": "BALANCE", "direction": "NEUTRAL", "value_acceptance": "NEUTRAL", "confidence": 0.0}
    context = MockContextRegistry(vwap_z_score=1.0, regime_v2_data=regime_data)
    res = check_regime_alignment(symbol, "LONG", {"price": 60000}, context)
    if res.passed and res.setup_mode == SetupMode.CONTINUATION:
        logger.info("✅ Passed (Rotation/Continuation)")
    else:
        logger.error(
            f"❌ Failed: expected passed=True, setup_mode=CONTINUATION, got passed={res.passed}, mode={res.setup_mode}"
        )
        all_passed = False

    # Case 3: TREND + ACCEPTING + Trend-Aligned -> CONTINUATION
    logger.info("\n--- Case 3: TREND + ACCEPTING + Trend-Aligned -> CONTINUATION ---")
    regime_data = {"regime": "TREND_UP", "direction": "UP", "value_acceptance": "ACCEPTING", "confidence": 0.8}
    context = MockContextRegistry(vwap_z_score=2.5, regime_v2_data=regime_data)
    res = check_regime_alignment(symbol, "LONG", {"price": 60000}, context)
    if res.passed and res.setup_mode == SetupMode.CONTINUATION:
        logger.info("✅ Passed (Trend Continuation)")
    else:
        logger.error(
            f"❌ Failed: expected passed=True, setup_mode=CONTINUATION, got passed={res.passed}, mode={res.setup_mode}"
        )
        all_passed = False

    # Case 4: TREND + REJECTING + Counter-Trend + EXCESS -> REVERSION
    logger.info("\n--- Case 4: TREND + REJECTING + Counter-Trend + EXCESS -> REVERSION ---")
    regime_data = {"regime": "TREND_UP", "direction": "UP", "value_acceptance": "REJECTING", "confidence": 0.8}
    context = MockContextRegistry(vwap_z_score=3.5, regime_v2_data=regime_data)  # > 3.0 is EXCESS
    res = check_regime_alignment(symbol, "SHORT", {"price": 60000}, context)  # Counter trend
    if res.passed and res.setup_mode == SetupMode.REVERSION:
        logger.info("✅ Passed (Absorption Reversion at Excess)")
    else:
        logger.error(
            f"❌ Failed: expected passed=True, setup_mode=REVERSION, got passed={res.passed}, mode={res.setup_mode}"
        )
        all_passed = False

    # Case 5: TREND + ACCEPTING + Counter-Trend -> BLOCKED
    logger.info("\n--- Case 5: TREND + ACCEPTING + Counter-Trend -> BLOCKED ---")
    regime_data = {"regime": "TREND_UP", "direction": "UP", "value_acceptance": "ACCEPTING", "confidence": 0.8}
    context = MockContextRegistry(vwap_z_score=2.5, regime_v2_data=regime_data)
    res = check_regime_alignment(symbol, "SHORT", {"price": 60000}, context)
    if not res.passed:
        logger.info("✅ Passed (Blocked counter-trend successfully)")
    else:
        logger.error("❌ Failed: expected passed=False to block counter-trend!")
        all_passed = False

    # Case 6: TREND + NEUTRAL + Counter-Trend -> BLOCKED if high conf
    logger.info("\n--- Case 6: TREND + NEUTRAL + Counter-Trend (High Conf) -> BLOCKED ---")
    regime_data = {"regime": "TREND_UP", "direction": "UP", "value_acceptance": "NEUTRAL", "confidence": 0.8}
    context = MockContextRegistry(vwap_z_score=2.5, regime_v2_data=regime_data)
    res = check_regime_alignment(symbol, "SHORT", {"price": 60000}, context)
    if not res.passed:
        logger.info("✅ Passed (Blocked counter-trend in high conf trend)")
    else:
        logger.error("❌ Failed: expected passed=False to block counter-trend!")
        all_passed = False

    # Case 7: Z-Score Disambiguation
    logger.info("\n--- Case 7: Z-Score Disambiguation ---")
    # Footprint Z = 4.0 (EXCESS), but VWAP Z = 1.0 (IN_VALUE)
    # With BALANCE, this should trigger IN_VALUE Rotation, NOT OUT_OF_VALUE Reversion
    regime_data = {"regime": "BALANCE", "direction": "NEUTRAL", "value_acceptance": "NEUTRAL", "confidence": 0.0}
    context = MockContextRegistry(vwap_z_score=1.0, regime_v2_data=regime_data)
    res = check_regime_alignment(symbol, "LONG", {"price": 60000, "z_score": 4.0}, context)
    if res.passed and res.setup_mode == SetupMode.CONTINUATION:
        logger.info("✅ Passed (Used VWAP Z-score for value position correctly)")
    else:
        logger.error(f"❌ Failed: System fell back to footprint Z-score incorrectly! got mode={res.setup_mode}")
        all_passed = False

    return all_passed


if __name__ == "__main__":
    all_passed = run_tests()
    if all_passed:
        logger.info("\n✅ ALL REGIME GUARDIAN TESTS PASSED")
        sys.exit(0)
    else:
        logger.error("\n❌ SOME REGIME GUARDIAN TESTS FAILED")
        sys.exit(1)
