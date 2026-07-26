"""
Signal Arbitrator Validator - VA_GATE Regime Gating Check
-------------------------------------------------------
Validates that the SignalArbitrator correctly blocks or allows
signals (TacticalAbsorption, TrendAcceptance, etc.) depending on
the active market regime (TRENDING vs RANGE) via the VA_GATE.
"""

import logging
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from decision.signal_arbitrator import SignalArbitrator


def setup_logging():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(name)-25s | %(message)s", handlers=[logging.StreamHandler()]
    )


logger = logging.getLogger("ArbitratorValidator")


def run_tests():
    logger.info("=" * 60)
    logger.info("🛡️  SIGNAL ARBITRATOR & VA_GATE VALIDATOR")
    logger.info("=" * 60)

    # 1. Setup Mock Environment
    mock_pressure = MagicMock()
    mock_context = MagicMock()
    arbitrator = SignalArbitrator(pressure_engine=mock_pressure, context_registry=mock_context)

    mock_profile = {
        "va_gate": {
            "block_in_trending": ["failed_breakout", "liquidity_exhaustion", "tactical_absorption"],
            "block_in_range": ["trend_acceptance"],
        }
    }

    candidates = [
        {"scenario": "tactical_absorption", "side": "LONG", "score": 1.0},
        {"scenario": "trend_acceptance", "side": "LONG", "score": 1.0},
        {"scenario": "failed_breakout", "side": "SHORT", "score": 1.0},
    ]

    failures = 0

    with patch("decision.signal_arbitrator.profile_manager") as mock_profile_manager, patch(
        "decision.regime_classifier.regime_classifier"
    ) as mock_regime_classifier:

        mock_profile_manager.get_profile.return_value = mock_profile

        # --- TEST 1: TRENDING REGIME ---
        logger.info("\n▶️ TEST 1: TRENDING Regime")
        mock_regime_classifier.classify.return_value = ("TRENDING", {"trend_votes": 3})

        filtered_trending = arbitrator._apply_va_gate("LTCUSDT", candidates.copy())
        allowed_scenarios = [s["scenario"] for s in filtered_trending]

        logger.info(f"Candidates before: {[s['scenario'] for s in candidates]}")
        logger.info(f"Candidates after : {allowed_scenarios}")

        if "tactical_absorption" in allowed_scenarios:
            logger.error("❌ ERROR: tactical_absorption should be blocked in TRENDING")
            failures += 1
        if "failed_breakout" in allowed_scenarios:
            logger.error("❌ ERROR: failed_breakout should be blocked in TRENDING")
            failures += 1
        if "trend_acceptance" not in allowed_scenarios:
            logger.error("❌ ERROR: trend_acceptance should be ALLOWED in TRENDING")
            failures += 1

        if failures == 0:
            logger.info("✅ TRENDING Regime Gating PASS")

        # --- TEST 2: RANGE REGIME ---
        logger.info("\n▶️ TEST 2: RANGE Regime")
        mock_regime_classifier.classify.return_value = ("RANGE", {"trend_votes": -1})

        filtered_range = arbitrator._apply_va_gate("LTCUSDT", candidates.copy())
        allowed_scenarios_range = [s["scenario"] for s in filtered_range]

        logger.info(f"Candidates before: {[s['scenario'] for s in candidates]}")
        logger.info(f"Candidates after : {allowed_scenarios_range}")

        if "trend_acceptance" in allowed_scenarios_range:
            logger.error("❌ ERROR: trend_acceptance should be blocked in RANGE")
            failures += 1
        if "tactical_absorption" not in allowed_scenarios_range:
            logger.error("❌ ERROR: tactical_absorption should be ALLOWED in RANGE")
            failures += 1

        if failures == 0:
            logger.info("✅ RANGE Regime Gating PASS")

        # --- TEST 3: ARBITRATION CONFLICT RESOLUTION ---
        logger.info("\n▶️ TEST 3: Conflict Resolution (LONG vs SHORT)")
        # Provide both LONG and SHORT to on_tick. We must mock the detectors first.
        mock_fb = MagicMock()
        mock_fb.on_tick.return_value = {"scenario": "failed_breakout", "side": "SHORT", "score": 1.0}

        mock_ta = MagicMock()
        mock_ta.on_tick.return_value = {"scenario": "trend_acceptance", "side": "LONG", "score": 1.0}

        mock_le = MagicMock()
        mock_le.on_tick.return_value = None

        arbitrator.scenarios = [mock_fb, mock_ta, mock_le]

        # We simulate RANGE so TA is blocked, FB is allowed
        mock_regime_classifier.classify.return_value = ("RANGE", {})

        winner = arbitrator.on_tick("LTCUSDT", 100.0, 123456789.0, {})

        if not winner:
            logger.error("❌ ERROR: Should have resolved a winner")
            failures += 1
        else:
            logger.info(f"Winner scenario: {winner.get('scenario')} | Side: {winner.get('side')}")
            if winner.get("scenario") != "failed_breakout":
                logger.error("❌ ERROR: failed_breakout should have won since TA is blocked in RANGE")
                failures += 1

        if failures == 0:
            logger.info("✅ Conflict Resolution PASS")

    logger.info("\n" + "=" * 60)
    if failures == 0:
        logger.info("🏆 ALL SIGNAL ARBITRATOR TESTS PASSED")
        sys.exit(0)
    else:
        logger.error(f"❌ {failures} TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    setup_logging()
    run_tests()
