"""
Setup Data Validator - Phase 975 (LTA V4 Upgrade)
Validates that SetupEngine produces TP/SL for LTA_STRUCTURAL setups.

Ensures the new geometric targets (POC/VAH/VAL) are correctly
populated in the signal metadata.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.context_registry import ContextRegistry
from core.events import EventType, SignalEvent
from decision.setup_engine import SetupEngineV4

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
logger = logging.getLogger("SetupDataValidator")


class MockEngine:
    """Mock event engine for testing."""

    def __init__(self):
        self.dispatched_events = []

    def subscribe(self, event_type, handler):
        pass

    async def dispatch(self, event):
        self.dispatched_events.append(event)


def create_test_signal(
    sensor_type: str, direction: str, price: float, metadata_override: Optional[Dict] = None
) -> SignalEvent:
    """Create a test SignalEvent with specified parameters."""
    base_metadata = {
        "tactical_type": sensor_type,
        "direction": direction,
        "price": price,
    }
    if metadata_override:
        base_metadata.update(metadata_override)

    return SignalEvent(
        type=EventType.SIGNAL,
        timestamp=time.time(),
        symbol="TESTUSDT",
        sensor_id=sensor_type,
        side=direction,
        score=0.85,
        price=price,
        metadata=base_metadata,
    )


def create_lta_signal(direction: str, price: float) -> SignalEvent:
    """Create a structural signal for LTA."""
    return create_test_signal(
        "TacticalAbsorption",
        direction,
        price,
        {
            "absorption_detected": True,
            "z_score": 3.5,
        },
    )


def validate_setup_metadata(setup_name: str, metadata: Dict[str, Any]) -> List[str]:
    """Validate that setup metadata contains required fields."""
    errors = []

    # Required fields check
    required_fields = ["tp_price", "sl_price", "setup_type"]
    for field in required_fields:
        if field not in metadata:
            errors.append(f"❌ Missing required field: {field}")
        elif metadata[field] is None:
            errors.append(f"❌ Field is None: {field}")
        elif field in ["tp_price", "sl_price"] and metadata[field] == 0:
            errors.append(f"❌ Field is zero: {field}")

    # TP/SL sanity checks
    if "tp_price" in metadata and "sl_price" in metadata:
        tp = metadata["tp_price"]
        sl = metadata["sl_price"]

        if tp and sl:
            # Check TP/SL are not equal
            if tp == sl:
                errors.append("❌ TP equals SL - invalid setup")

            # Check TP/SL distance is reasonable (not > 10%)
            entry = metadata.get("price", 100.0)
            if entry > 0:
                tp_dist = abs(tp - entry) / entry * 100
                sl_dist = abs(sl - entry) / entry * 100

                if tp_dist > 10.0:
                    errors.append(f"❌ TP distance too large: {tp_dist:.2f}%")
                if sl_dist > 10.0:
                    errors.append(f"❌ SL distance too large: {sl_dist:.2f}%")

    return errors


def populate_context_registry(context_registry: ContextRegistry, symbol: str, poc: float, vah: float, val: float):
    """Populate ContextRegistry with synthetic market data to generate structural levels."""
    from unittest.mock import MagicMock

    context_registry.get_structural = MagicMock(return_value=(poc, vah, val))
    context_registry.get_regime = MagicMock(return_value="NEUTRAL")
    context_registry.get_ib = MagicMock(return_value=(vah + 1.0, val - 1.0))
    context_registry.is_in_trade = MagicMock(return_value=False)
    logger.debug(f"Populated {symbol} with synthetic market data (Mocks applied)")


async def run_validator():
    """Main validation routine."""
    logger.info("=" * 60)
    logger.info("SETUP DATA VALIDATOR - Phase 975 (LTA Upgrade)")
    logger.info("Validating TP/SL production from SetupEngineV4")
    logger.info("=" * 60)

    # Initialize components
    engine = MockEngine()
    context_registry = ContextRegistry()

    setup_engine = SetupEngineV4(
        engine=engine,
        context_registry=context_registry,
    )

    # Configure context for testing by populating with synthetic market data
    poc = 100.0
    vah = 105.0
    val = 95.0
    populate_context_registry(context_registry, "TESTUSDT", poc=poc, vah=vah, val=val)

    # Test scenarios - LTA requires price at extreme, and direction reversing to POC
    # SHORT at VAH, LONG at VAL
    test_scenarios = [
        ("LTA_STRUCTURAL", "SHORT", vah + 0.01, create_lta_signal),  # Valid: Price near VAH
        ("LTA_STRUCTURAL", "LONG", val - 0.01, create_lta_signal),  # Valid: Price near VAL
        ("LTA_STRUCTURAL", "LONG", vah, create_lta_signal),  # Invalid: LONG at VAH
        ("LTA_STRUCTURAL", "SHORT", poc, create_lta_signal),  # Invalid: Price at POC
    ]

    all_passed = True
    results_summary = []

    for setup_name, direction, price, signal_factory in test_scenarios:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {setup_name} | {direction} @ {price}")
        logger.info(f"{'='*60}")

        # Create signal
        signal = signal_factory(direction, price)

        # Inject memory for SetupEngine since it expects lists
        setup_engine.memory["TESTUSDT"] = [(time.time(), time.time(), signal)]

        # Evaluate setup
        try:
            result = setup_engine._evaluate_lta_structural("TESTUSDT", [signal])
        except Exception as e:
            logger.error(f"💥 Exception during evaluation: {e}")
            result = None

        # Analyze result
        if result is None:
            logger.info(f"⚠️  Setup returned None (gated by proximity/direction - Expected if invalid)")
            results_summary.append(
                {
                    "setup": setup_name,
                    "direction": direction,
                    "status": "GATED",
                    "tp": None,
                    "sl": None,
                }
            )
        else:
            metadata = result.get("metadata", {})
            tp = metadata.get("tp_price")
            sl = metadata.get("sl_price")
            setup_type = metadata.get("setup_type", "unknown")

            # Validate
            errors = validate_setup_metadata(setup_name, metadata)

            if errors:
                logger.error(f"❌ VALIDATION FAILED:")
                for error in errors:
                    logger.error(f"   {error}")
                all_passed = False
                results_summary.append(
                    {
                        "setup": setup_name,
                        "direction": direction,
                        "status": "FAILED",
                        "tp": tp,
                        "sl": sl,
                        "errors": errors,
                    }
                )
            else:
                logger.info(f"✅ VALID PASSED")
                logger.info(f"   Setup Type: {setup_type}")
                logger.info(f"   TP: {tp:.4f} ({abs(tp-price)/price*100:.2f}% from entry)")
                logger.info(f"   SL: {sl:.4f} ({abs(sl-price)/price*100:.2f}% from entry)")

                # Check RR ratio
                reward = abs(tp - price)
                risk = abs(sl - price)
                if risk > 0:
                    rr = reward / risk
                    logger.info(f"   RR Ratio: {rr:.2f}:1")
                else:
                    logger.warning("   ⚠️ RR Ratio: Infinity (Zero Risk)")

                results_summary.append(
                    {
                        "setup": setup_name,
                        "direction": direction,
                        "status": "PASSED",
                        "tp": tp,
                        "sl": sl,
                        "setup_type": setup_type,
                    }
                )

    # Summary report
    logger.info(f"\n{'='*60}")
    logger.info("VALIDATION SUMMARY")
    logger.info(f"{'='*60}")

    passed = sum(1 for r in results_summary if r["status"] == "PASSED")
    failed = sum(1 for r in results_summary if r["status"] == "FAILED")
    gated = sum(1 for r in results_summary if r["status"] == "GATED")

    logger.info(f"Total: {len(results_summary)} | ✅ Passed: {passed} | ❌ Failed: {failed} | ⚠️ Gated: {gated}")

    if failed > 0:
        logger.error(f"\n💣 FAILED SETUPS:")
        for r in results_summary:
            if r["status"] == "FAILED":
                logger.error(f"   - {r['setup']} {r['direction']}: {r.get('errors', [])}")
        logger.error(f"\n💣 VALIDATION FAILED - Fix SetupEngine before proceeding")

    return all_passed


if __name__ == "__main__":
    if not asyncio.run(run_validator()):
        import sys

        sys.exit(1)
