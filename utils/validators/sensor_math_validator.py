import asyncio
import logging
import os
import sys

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.context_registry import ContextRegistry
from core.events import AggregatedSignalEvent, EventType
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
    context_registry = ContextRegistry()

    player = AdaptivePlayer(
        engine=engine,
        croupier=croupier,
        fixed_pct=0.01,
        use_kelly=False,
        context_registry=context_registry,
    )

    # Test Scenarios
    scenarios = [
        # Scenario 1: SHORT at VAH (Reversion) - Fixed prices for SHORT
        {
            "name": "SHORT Reversion at VAH",
            "symbol": "DOTUSDT",
            "side": "SHORT",
            "metadata": {
                "setup_type": "reversion",
                "price": 100.0,
                "1h_poc": 95.0,
                "1h_vah": 105.0,  # SL should be above entry
                "1h_val": 90.0,
                "tp_price": 99.80,  # 0.20% TP
                "sl_price": 100.02,  # structural SL
            },
        },
        # Scenario 2: LONG at VAL (Reversion)
        {
            "name": "LONG Reversion at VAL",
            "symbol": "DOTUSDT",
            "side": "LONG",
            "metadata": {
                "setup_type": "reversion",
                "price": 90.0,
                "1h_poc": 95.0,
                "1h_vah": 100.0,
                "1h_val": 89.5,
                "tp_price": 90.18,
                "sl_price": 89.98,
            },
        },
        # Scenario 3: SHORT Continuation
        {
            "name": "SHORT Continuation",
            "symbol": "KAVAUSDT",
            "side": "SHORT",
            "metadata": {
                "setup_type": "continuation",
                "price": 90.0,
                "1h_poc": 95.0,
                "1h_vah": 100.0,
                "1h_val": 92.0,
                "tp_price": 89.73,
                "sl_price": 90.27,
            },
        },
        # Scenario 4: DOTUSDT crash data (Inversion suspected)
        {
            "name": "SHORT DOTUSDT Real Data Suspect",
            "symbol": "DOTUSDT",
            "side": "SHORT",
            "metadata": {
                "price": 1.495,
                "poc": 1.405,  # TP below entry for SHORT
                "vah": 1.515,
                "val": 1.385,
                "tp_price": 1.490,
                "sl_price": 1.500,
            },
        },
        # Scenario 5: TREND_WINDOW (Aggressive Target)
        {
            "name": "LONG TREND (Post-Breakout)",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "regime": "TREND_WINDOW",
            "expect_reject": False,  # Phase 970: Dumb Player no longer performs RR filtering
            "metadata": {
                "setup_type": "continuation",
                "price": 60500.0,
                "vah": 60600.0,  # TP
                "val": 60200.0,
                "poc": 60300.0,
                "tp_price": 60621,
                "sl_price": 60400,
            },
        },
        # Scenario 6: RANGE_WINDOW (Mean Reversion)
        {
            "name": "SHORT RANGE (Mean Reversion)",
            "symbol": "ETHUSDT",
            "side": "SHORT",
            "regime": "RANGE_WINDOW",
            "metadata": {
                "setup_type": "reversion",
                "price": 2510.0,
                "vah": 2515.0,
                "val": 2485.0,
                "poc": 2500.0,
                "atr_1m": 5.0,
                "tp_price": 2505.0,
                "sl_price": 2512.0,
            },
        },
        # Scenario 7: ATR Breathing Room Floor
        {
            "name": "ATR Floor (SL Expansion)",
            "symbol": "LTCUSDT",
            "side": "LONG",
            "metadata": {
                "setup_type": "reversion",
                "price": 100.0,
                "1h_poc": 102.0,
                "1h_vah": 105.0,
                "1h_val": 99.8,
                "atr_1m": 1.0,
                "tp_price": 102.0,
                "sl_price": 99.7,
            },
        },
    ]

    failed_scenarios = []

    for s in scenarios:
        logger.info(f"\n--- Testing Scenario: {s['name']} ---")
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

        if "regime" in s:
            context_registry.set_regime(s["symbol"], s["regime"])
        else:
            context_registry.set_regime(s["symbol"], "NORMAL")

        await player.on_aggregated_signal(event)
        await asyncio.sleep(0.1)

        if not engine.dispatched_events:
            if s.get("expect_reject"):
                logger.info(f"✅ Scenario {s['name']} correctly REJECTED.")
                continue
            else:
                logger.error(f"❌ Scenario {s['name']} failed to dispatch a DecisionEvent.")
                failed_scenarios.append(s["name"])
                continue
        elif s.get("expect_reject"):
            logger.error(f"❌ Scenario {s['name']} dispatched a decision but was EXPECTED to REJECT.")
            failed_scenarios.append(s["name"])
            continue

        decision = engine.dispatched_events[0]
        tp = decision.tp_price
        sl = decision.sl_price
        entry = s["metadata"].get("price")

        logger.info(f"Result for {s['side']} @ {entry}: TP={tp}, SL={sl}")

        scenario_failed = False
        if decision.side == "LONG":
            if tp is not None and tp <= entry:
                logger.error(f"❌ MATH INVERSION: LONG TP ({tp}) is NOT strictly > entry ({entry})")
                scenario_failed = True
            if sl is not None and sl >= entry:
                logger.error(f"❌ MATH INVERSION: LONG SL ({sl}) is NOT strictly < entry ({entry})")
                scenario_failed = True
        elif decision.side == "SHORT":
            if tp is not None and tp >= entry:
                logger.error(f"❌ MATH INVERSION: SHORT TP ({tp}) is NOT strictly < entry ({entry})")
                scenario_failed = True
            if sl is not None and sl <= entry:
                logger.error(f"❌ MATH INVERSION: SHORT SL ({sl}) is NOT strictly > entry ({entry})")
                scenario_failed = True

        if scenario_failed:
            failed_scenarios.append(str(s["name"]))

    if failed_scenarios:
        logger.error(f"\n💣 VALIDATION FAILED on scenarios: {', '.join(failed_scenarios)}")
        sys.exit(1)
    else:
        logger.info("\n✅ All scenarios passed gracefully. No Math Inversions in AdaptivePlayer.")


if __name__ == "__main__":
    asyncio.run(run_validator())
