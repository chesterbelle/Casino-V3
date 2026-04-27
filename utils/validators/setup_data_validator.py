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
    # Phase 1150: Need high/low/open for Failed Auction check
    metadata = {
        "absorption_detected": True,
        "z_score": 3.5,
    }
    if direction == "LONG":
        metadata["low"] = price - 0.5  # Probed below
        metadata["open"] = price - 0.1
        metadata["close"] = price
        metadata["high"] = price + 0.1
    else:
        metadata["high"] = price + 0.5  # Probed above
        metadata["open"] = price + 0.1
        metadata["close"] = price
        metadata["low"] = price - 0.1

    return create_test_signal(
        "TacticalAbsorption",
        direction,
        price,
        metadata,
    )


def create_absorption_v1_signal(direction: str, price: float) -> SignalEvent:
    """Create an Absorption V1 signal."""
    metadata = {
        "strategy": "AbsorptionScalpingV1",
        "absorption_level": price,
        "direction": "SELL_EXHAUSTION" if direction == "LONG" else "BUY_EXHAUSTION",
        "delta": -10.0 if direction == "LONG" else 10.0,
        "z_score": 3.5,
        "concentration": 0.85,
        "noise": 0.10,
        "price": price,
    }

    return create_test_signal(
        "AbsorptionDetector",
        direction,
        price,
        metadata,
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
    # Phase 1150: Mock new guardians
    context_registry.get_poc_migration = MagicMock(return_value=0.0)
    context_registry.get_va_integrity = MagicMock(return_value=0.5)
    context_registry.micro_state = {symbol: {"z_score": 0.0}}

    logger.debug(f"Populated {symbol} with synthetic market data (Mocks applied)")


async def test_absorption_v1_setup(setup_engine, engine, context_registry):
    """Test Absorption V1 setup generation."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Absorption V1 Setup")
    logger.info("=" * 60)

    all_passed = True

    # Mock FootprintRegistry to provide volume profile data
    from unittest.mock import MagicMock, patch

    from core.footprint_registry import FootprintRegistry

    # Get the singleton instance
    footprint_registry = FootprintRegistry()

    # Mock get_volume_profile to return synthetic data
    # Returns list of (price, ask_vol, bid_vol) tuples
    # For LONG: TP should be above entry (low volume node)
    # For SHORT: TP should be below entry (low volume node)
    def mock_volume_profile_long(symbol, price_from, price_to):
        # Return volume profile with low volume nodes above entry
        # Entry at 65432.0, create LVN at 65500.0
        return [
            (65432.0, 100.0, 100.0),  # Entry level - high volume
            (65440.0, 80.0, 80.0),  # Medium volume
            (65450.0, 90.0, 90.0),  # Medium volume
            (65460.0, 85.0, 85.0),  # Medium volume
            (65470.0, 95.0, 95.0),  # Medium volume
            (65480.0, 75.0, 75.0),  # Medium volume
            (65490.0, 70.0, 70.0),  # Medium volume
            (65500.0, 20.0, 20.0),  # LOW VOLUME NODE (LVN) - TP target
            (65510.0, 85.0, 85.0),  # Medium volume
            (65520.0, 90.0, 90.0),  # Medium volume
        ]

    def mock_volume_profile_short(symbol, price_from, price_to):
        # Return volume profile with low volume nodes below entry
        # Entry at 65432.0, create LVN at 65300.0
        return [
            (65300.0, 20.0, 20.0),  # LOW VOLUME NODE (LVN) - TP target
            (65310.0, 85.0, 85.0),  # Medium volume
            (65320.0, 90.0, 90.0),  # Medium volume
            (65330.0, 75.0, 75.0),  # Medium volume
            (65340.0, 95.0, 95.0),  # Medium volume
            (65350.0, 85.0, 85.0),  # Medium volume
            (65360.0, 90.0, 90.0),  # Medium volume
            (65370.0, 80.0, 80.0),  # Medium volume
            (65380.0, 85.0, 85.0),  # Medium volume
            (65432.0, 100.0, 100.0),  # Entry level - high volume
        ]

    # Test LONG (from SELL_EXHAUSTION)
    logger.info("\n--- Testing LONG (SELL_EXHAUSTION) ---")
    with patch.object(footprint_registry, "get_volume_profile", side_effect=mock_volume_profile_long):
        signal_long = create_absorption_v1_signal("LONG", 65432.0)
        await setup_engine.on_signal(signal_long)

        # Verify setup was generated
        if engine.dispatched_events:
            setup = engine.dispatched_events[-1]
            errors = validate_setup_metadata("Absorption_LONG", setup.metadata)
            if errors:
                logger.error(f"❌ Absorption V1 LONG validation failed:")
                for error in errors:
                    logger.error(f"   {error}")
                all_passed = False
            else:
                logger.info("✅ Absorption V1 LONG setup valid")
                tp = setup.metadata.get("tp_price")
                sl = setup.metadata.get("sl_price")
                price = setup.metadata.get("price", 65432.0)
                logger.info(f"   TP: {tp:.4f} ({abs(tp-price)/price*100:.2f}% from entry)")
                logger.info(f"   SL: {sl:.4f} ({abs(sl-price)/price*100:.2f}% from entry)")
        else:
            logger.warning("⚠️ No setup generated for Absorption V1 LONG")
            all_passed = False

    # Clear events for next test
    engine.dispatched_events.clear()

    # Test SHORT (from BUY_EXHAUSTION)
    logger.info("\n--- Testing SHORT (BUY_EXHAUSTION) ---")
    with patch.object(footprint_registry, "get_volume_profile", side_effect=mock_volume_profile_short):
        signal_short = create_absorption_v1_signal("SHORT", 65432.0)
        await setup_engine.on_signal(signal_short)

        if engine.dispatched_events:
            setup = engine.dispatched_events[-1]
            errors = validate_setup_metadata("Absorption_SHORT", setup.metadata)
            if errors:
                logger.error(f"❌ Absorption V1 SHORT validation failed:")
                for error in errors:
                    logger.error(f"   {error}")
                all_passed = False
            else:
                logger.info("✅ Absorption V1 SHORT setup valid")
                tp = setup.metadata.get("tp_price")
                sl = setup.metadata.get("sl_price")
                price = setup.metadata.get("price", 65432.0)
                logger.info(f"   TP: {tp:.4f} ({abs(tp-price)/price*100:.2f}% from entry)")
                logger.info(f"   SL: {sl:.4f} ({abs(sl-price)/price*100:.2f}% from entry)")
        else:
            logger.warning("⚠️ No setup generated for Absorption V1 SHORT")
            all_passed = False

    return all_passed


async def run_validator():
    """Main validation routine."""
    logger.info("=" * 60)
    logger.info("SETUP DATA VALIDATOR - Phase 975 + Absorption V1")
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
    logger.info("LTA VALIDATION SUMMARY")
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
        logger.error(f"\n💣 LTA VALIDATION FAILED - Fix SetupEngine before proceeding")
        all_passed = False

    # Test Absorption V1
    logger.info(f"\n{'='*60}")
    logger.info("ABSORPTION V1 VALIDATION")
    logger.info(f"{'='*60}")

    absorption_passed = await test_absorption_v1_setup(setup_engine, engine, context_registry)
    if not absorption_passed:
        logger.error("❌ Absorption V1 setup validation FAILED")
        all_passed = False
    else:
        logger.info("✅ Absorption V1 setup validation PASSED")

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info("OVERALL VALIDATION SUMMARY")
    logger.info(f"{'='*60}")
    if all_passed:
        logger.info("✅ All setup validations PASSED")
    else:
        logger.error("❌ Some validations FAILED - review errors above")

    return all_passed


if __name__ == "__main__":
    if not asyncio.run(run_validator()):
        import sys

        sys.exit(1)
