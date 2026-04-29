"""
Setup Data Validator - Phase 7: Absorption V1 Only
---------------------------------------------------
Validates that AbsorptionSetupEngine produces valid TP/SL prices.

LTA V4/V5/V6 tests PURGED - Absorption V1 is the sole strategy.

Usage:
    python utils/validators/setup_data_validator.py
"""

import asyncio
import logging
import os
import sys
import time
from unittest.mock import patch

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.context_registry import ContextRegistry
from core.events import EventType, SignalEvent
from core.footprint_registry import footprint_registry
from decision.setup_engine import SetupEngineV4

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("SetupDataValidator")


class MockEngine:
    def __init__(self):
        self.dispatched_events = []

    def subscribe(self, event_type, handler):
        pass

    async def dispatch(self, event):
        self.dispatched_events.append(event)


def create_absorption_v1_signal(side: str, price: float) -> SignalEvent:
    """Create a mock Absorption V1 signal."""
    direction = "SELL_EXHAUSTION" if side == "LONG" else "BUY_EXHAUSTION"

    return SignalEvent(
        type=EventType.SIGNAL,
        timestamp=time.time(),
        symbol="BTC/USDT:USDT",
        sensor_name="AbsorptionDetector",
        timeframe="1m",
        side=side,
        price=price,
        score=0.9,
        metadata={
            "level": price,
            "absorption_level": price,
            "direction": direction,
            "delta": -100.0 if direction == "SELL_EXHAUSTION" else 100.0,
            "z_score": 3.5,
            "concentration": 0.80,
            "noise": 0.15,
            "ask_volume": 10.0 if direction == "SELL_EXHAUSTION" else 100.0,
            "bid_volume": 100.0 if direction == "SELL_EXHAUSTION" else 10.0,
        },
    )


def validate_setup_metadata(setup_name: str, metadata: dict) -> list:
    """Validate setup metadata has required fields."""
    errors = []

    # Required fields
    required = ["tp_price", "sl_price", "price"]
    for field in required:
        if field not in metadata or metadata[field] is None:
            errors.append(f"Missing or None: {field}")

    # TP/SL must be non-zero
    tp = metadata.get("tp_price", 0)
    sl = metadata.get("sl_price", 0)
    price = metadata.get("price", 0)

    if tp == 0:
        errors.append("tp_price is 0")
    if sl == 0:
        errors.append("sl_price is 0")
    if price == 0:
        errors.append("price is 0")

    # Math inversion check
    side = metadata.get("side", "UNKNOWN")
    if side == "LONG":
        if tp <= price:
            errors.append(f"LONG: TP ({tp}) <= entry ({price})")
        if sl >= price:
            errors.append(f"LONG: SL ({sl}) >= entry ({price})")
    elif side == "SHORT":
        if tp >= price:
            errors.append(f"SHORT: TP ({tp}) >= entry ({price})")
        if sl <= price:
            errors.append(f"SHORT: SL ({sl}) <= entry ({price})")

    return errors


async def test_absorption_v1_setup() -> bool:
    """Test Absorption V1 setup generation."""
    logger.info("\n" + "=" * 60)
    logger.info("ABSORPTION V1 SETUP VALIDATION")
    logger.info("=" * 60)

    engine = MockEngine()
    context_registry = ContextRegistry()
    setup_engine = SetupEngineV4(engine=engine, context_registry=context_registry)

    all_passed = True

    # Mock FootprintRegistry.get_volume_profile to return synthetic LVNs
    def mock_volume_profile_long(symbol, price_from, price_to):
        # Return volume profile with low volume nodes above entry
        # Entry at 65432.0, create LVN at 65550.0
        return [
            (65432.0, 100.0, 100.0),  # Entry level - high volume
            (65440.0, 85.0, 85.0),  # Medium volume
            (65450.0, 90.0, 90.0),  # Medium volume
            (65460.0, 75.0, 75.0),  # Medium volume
            (65470.0, 95.0, 95.0),  # Medium volume
            (65480.0, 85.0, 85.0),  # Medium volume
            (65490.0, 90.0, 90.0),  # Medium volume
            (65500.0, 80.0, 80.0),  # Medium volume
            (65510.0, 85.0, 85.0),  # Medium volume
            (65550.0, 20.0, 20.0),  # LOW VOLUME NODE (LVN) - TP target
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
    logger.info("SETUP DATA VALIDATOR - Absorption V1 Only")
    logger.info("Validating TP/SL production from AbsorptionSetupEngine")
    logger.info("=" * 60)

    all_passed = await test_absorption_v1_setup()

    logger.info("\n" + "=" * 60)
    if all_passed:
        logger.info("✅ ALL TESTS PASSED")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("❌ SOME TESTS FAILED")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_validator())
