import asyncio
import logging
import os
import sys

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.events import EventType
from decision.aggregator import AggregatedSignalEvent
from players.adaptive import AdaptivePlayer, DecisionEvent

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
logger = logging.getLogger("SensorMathValidator")


class MockEngine:
    def __init__(self):
        self.dispatched_events = []

    def subscribe(self, event_type, handler):
        pass

    async def dispatch(self, event):
        self.dispatched_events.append(event)


class MockCroupier:
    def get_active_positions(self):
        return []

    def get_equity(self):
        return 1000.0

    def is_pending(self, symbol):
        return False


async def run_validator():
    logger.info("Starting Sensor Math Validator...")

    engine = MockEngine()
    croupier = MockCroupier()

    player = AdaptivePlayer(engine=engine, croupier=croupier, fixed_pct=0.01, use_kelly=False)

    # Test Scenarios
    scenarios = [
        # Scenario 1: SHORT at VAH (Reversion)
        {
            "name": "SHORT Reversion at VAH",
            "symbol": "DOTUSDT",
            "side": "SHORT",
            "current_price": 100.0,
            "metadata": {
                "setup_type": "reversion",
                "price": 100.0,
                "1h_poc": 95.0,
                "1h_vah": 99.0,
                "1h_val": 90.0,
            },
        },
        # Scenario 2: LONG at VAL (Reversion)
        {
            "name": "LONG Reversion at VAL",
            "symbol": "DOTUSDT",
            "side": "LONG",
            "current_price": 90.0,
            "metadata": {
                "setup_type": "reversion",
                "price": 90.0,
                "1h_poc": 95.0,
                "1h_vah": 100.0,
                "1h_val": 89.5,
            },
        },
        # Scenario 3: SHORT Continuation
        {
            "name": "SHORT Continuation",
            "symbol": "KAVAUSDT",
            "side": "SHORT",
            "current_price": 90.0,  # Below VAL
            "metadata": {
                "setup_type": "continuation",
                "price": 90.0,
                "1h_poc": 95.0,
                "1h_vah": 100.0,
                "1h_val": 92.0,
            },
        },
        # Scenario 4: DOTUSDT crash data (Inversion suspected)
        {
            "name": "SHORT DOTUSDT Real Data Suspect",
            "symbol": "DOTUSDT",
            "side": "SHORT",
            "current_price": 1.495,
            "metadata": {
                # We will test without setup_type to fallback to Dalton Contextual Exits
                "price": 1.495,
                "poc": 1.505,
                "vah": 1.515,
                "val": 1.485,
            },
        },
    ]

    failed = False

    for s in scenarios:
        logger.info(f"\\n--- Testing Scenario: {s['name']} ---")
        engine.dispatched_events.clear()

        event = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=123.0,
            symbol=s["symbol"],
            candle_timestamp=123.0,
            selected_sensor="TestSensor",
            sensor_score=1.0,
            side=s["side"],
            confidence=1.0,
            total_signals=1,
            metadata=s["metadata"],
            strategy_name="TestStrategy",
            t0_timestamp=123.0,
            t1_decision_ts=123.1,
            trace_id="trc_test",
        )

        await player.on_aggregated_signal(event)
        await asyncio.sleep(0.1)

        if not engine.dispatched_events:
            logger.error(f"❌ Scenario {s['name']} failed to dispatch a DecisionEvent.")
            failed = True
            continue

        decision = engine.dispatched_events[0]
        tp = decision.tp_price
        sl = decision.sl_price
        entry = s["current_price"]

        logger.info(f"Result for {s['side']} @ {entry}: TP={tp}, SL={sl}")

        # Validations
        if decision.side == "LONG":
            if tp is not None and tp <= entry:
                logger.error(f"❌ MATH INVERSION: LONG TP ({tp}) is NOT strictly > entry ({entry})")
                failed = True
            if sl is not None and sl >= entry:
                logger.error(f"❌ MATH INVERSION: LONG SL ({sl}) is NOT strictly < entry ({entry})")
                failed = True
        elif decision.side == "SHORT":
            if tp is not None and tp >= entry:
                logger.error(f"❌ MATH INVERSION: SHORT TP ({tp}) is NOT strictly < entry ({entry})")
                failed = True
            if sl is not None and sl <= entry:
                logger.error(f"❌ MATH INVERSION: SHORT SL ({sl}) is NOT strictly > entry ({entry})")
                failed = True

    if failed:
        logger.error("\\n💣 VALIDATION FAILED: Math Inversions Detected!")
        sys.exit(1)
    else:
        logger.info("\\n✅ All scenarios passed gracefully. No Math Inversions in AdaptivePlayer.")


if __name__ == "__main__":
    asyncio.run(run_validator())
