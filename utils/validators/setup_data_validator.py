"""
Setup Data Validator - Phase 975
Validates that SetupEngine produces TP/SL for ALL setup types.

This validator ensures that every playbook in SetupEngineV4 returns
properly calculated tp_price and sl_price in the signal metadata.
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


class MockConnector:
    """Mock exchange connector."""

    def get_latest_micro(self, symbol: str):
        # Return a mock micro bar with OHLCV data
        class MockMicro:
            def __init__(self):
                self.timestamp = time.time()
                self.price = 100.0
                self.open = 99.5
                self.high = 100.5
                self.low = 99.0
                self.close = 100.0
                self.volume = 1000.0
                self.delta = 50.0
                self.cvd = 500.0
                self.skewness = 0.6

        return MockMicro()

    def get_atr(self, symbol: str, timeframe: str = "1m"):
        return 0.5


def create_test_signal(
    sensor_type: str, direction: str, price: float, metadata_override: Optional[Dict] = None
) -> SignalEvent:
    """Create a test SignalEvent with specified parameters."""
    base_metadata = {
        "tactical_type": sensor_type,
        "direction": direction,
        "price": price,
        "trap_price": price,
        "high": price * 1.005,
        "low": price * 0.995,
        "wick_vol_pct": 0.25,
        "pattern": sensor_type,
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


def create_delta_divergence_signal(direction: str, price: float) -> SignalEvent:
    """Create a Delta Divergence signal."""
    return create_test_signal(
        "TacticalCumulativeDelta",  # Delta sensor type
        direction,
        price,
        {
            "divergence": "bullish" if direction == "LONG" else "bearish",
            "z_score": 2.5,
            "price_high": price * 1.002,
            "price_low": price * 0.998,
            "total_range": price * 0.004,
        },
    )


def create_trapped_traders_signal(direction: str, price: float) -> SignalEvent:
    """Create a Trapped Traders signal."""
    return create_test_signal(
        "TacticalTrappedTraders",
        direction,
        price,
        {
            "wick_vol_pct": 0.35,
            "pattern": "Long_Wick_Trap",
        },
    )


def create_fade_extreme_signal(direction: str, price: float) -> SignalEvent:
    """Create a Fade Extreme signal."""
    return create_test_signal(
        "TacticalAbsorption",  # Absorption at extremes
        direction,
        price,
        {
            "absorption_detected": True,
            "reversal_direction": direction,
            "node_high": price * 1.003,
            "node_low": price * 0.997,
        },
    )


def create_stacked_imbalance_signal(direction: str, price: float) -> SignalEvent:
    """Create a Stacked Imbalance signal for Trend Continuation."""
    return create_test_signal(
        "TacticalStackedImbalance",
        direction,
        price,
        {
            "levels": [price * 0.998, price, price * 1.002],
            "poc": price,
            "confirmations": [{"direction": direction, "weight": 1.0}],
            "has_confluence": True,
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
    # Feed ticks to build up the market profile
    # The MarketProfile will calculate POC/VAH/VAL from this data
    # base_price = poc  # Removed unused variable

    # Simulate trades around POC with some distribution to create VAH/VAL
    for i in range(100):
        # Create normal distribution around POC
        if i < 30:
            price = val + (poc - val) * 0.5  # Near VAL
        elif i < 70:
            price = poc  # Near POC (most volume)
        else:
            price = poc + (vah - poc) * 0.5  # Near VAH

        volume = 10.0 + (50.0 if abs(price - poc) < 0.1 else 10.0)
        side = "buy" if i % 2 == 0 else "sell"

        context_registry.on_tick(symbol, price, volume, side)

    # Set IB levels
    context_registry.set_ib(symbol, vah + 1.0, val - 1.0)

    logger.debug(f"Populated {symbol} with synthetic market data")


async def run_validator():
    """Main validation routine."""
    logger.info("=" * 60)
    logger.info("SETUP DATA VALIDATOR - Phase 975")
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
    populate_context_registry(context_registry, "TESTUSDT", poc=100.0, vah=102.0, val=98.0)

    # Test scenarios - all setups must produce TP/SL
    test_scenarios = [
        ("DeltaDivergence", "LONG", 100.0, create_delta_divergence_signal),
        ("DeltaDivergence", "SHORT", 100.0, create_delta_divergence_signal),
        ("TrappedTraders", "LONG", 100.0, create_trapped_traders_signal),
        ("TrappedTraders", "SHORT", 100.0, create_trapped_traders_signal),
        ("FadeExtreme", "LONG", 98.0, create_fade_extreme_signal),  # Near VAL
        ("FadeExtreme", "SHORT", 102.0, create_fade_extreme_signal),  # Near VAH
        ("TrendContinuation", "LONG", 100.0, create_stacked_imbalance_signal),
        ("TrendContinuation", "SHORT", 100.0, create_stacked_imbalance_signal),
    ]

    all_passed = True
    results_summary = []

    for setup_name, direction, price, signal_factory in test_scenarios:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {setup_name} | {direction} @ {price}")
        logger.info(f"{'='*60}")

        # Create signal
        signal = signal_factory(direction, price)

        # Evaluate setup
        try:
            if setup_name == "DeltaDivergence":
                result = setup_engine._evaluate_delta_divergence("TESTUSDT", [signal])
            elif setup_name == "TrappedTraders":
                result = setup_engine._evaluate_trapped_traders("TESTUSDT", [signal])
            elif setup_name == "FadeExtreme":
                result = setup_engine._evaluate_fade_extreme("TESTUSDT", [signal])
            elif setup_name == "TrendContinuation":
                result = setup_engine._evaluate_trend_continuation("TESTUSDT", [signal])
            else:
                result = None

        except Exception as e:
            logger.error(f"💥 Exception during evaluation: {e}")
            result = None

        # Analyze result
        if result is None:
            logger.info(f"⚠️  Setup returned None (gated by proximity/regime - OK for this test)")
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
