import asyncio
import logging
import os
import sys

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.context_registry import ContextRegistry
from core.events import EventType, MicrostructureEvent, SignalEvent
from decision.setup_engine import SetupEngineV4

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
logger = logging.getLogger("SharkBreathValidator")


class MockEngine:
    def __init__(self):
        self.dispatched_events = []

    def subscribe(self, event_type, handler):
        pass

    async def dispatch(self, event):
        self.dispatched_events.append(event)


async def run_validator():
    logger.info("🧪 Starting Shark Breath (Volatility Climax) Validator...")

    engine = MockEngine()
    context_registry = ContextRegistry()
    setup_engine = SetupEngineV4(engine=engine, context_registry=context_registry, fast_track=True)

    # 1. Setup Context (VAH/VAL Boundaries)
    symbol = "BTCUSDT"

    # Mocking structural levels as ContextRegistry relies on MarketProfile
    context_registry.get_structural = lambda sym: (100.0, 105.0, 95.0)
    context_registry.get_ib = lambda sym: (103.0, 97.0)

    # 2. Test Scenario 1: LONG Shark Breath at VAL
    logger.info("📡 Testing Scenario: LONG Shark Breath at VAL")

    # Inject Microstructure (Price at VAL)
    micro = MicrostructureEvent(
        type=EventType.MICROSTRUCTURE, timestamp=1000.0, symbol=symbol, cvd=100.0, skewness=0.1, price=95.05
    )
    setup_engine.micro_memory[symbol].append((1000.0, 1000.0, micro))

    # Inject Volatility Spike
    spike_event = SignalEvent(
        type=EventType.SIGNAL,
        timestamp=1000.0,
        symbol=symbol,
        side="TACTICAL",
        sensor_id="VolatilitySpike",
        score=1.0,
        metadata={"type": "VOLATILITY_SPIKE", "ratio": 5.5, "timestamp": 1000.0},
    )

    # Process the signal
    await setup_engine.on_signal(spike_event)

    # Check results
    signals = engine.dispatched_events
    shark_signals = [s for s in signals if s.metadata.get("trigger") == "SharkBreath"]

    if not shark_signals:
        logger.error("❌ SharkBreath signal NOT detected at VAL!")
        return False

    s = shark_signals[0]
    logger.info(f"✅ SharkBreath LONG detected! Side: {s.side}")
    logger.info(f"   TP: {s.metadata['tp_price']} (Target: POC 100.0)")
    logger.info(f"   SL: {s.metadata['sl_price']} (Target: ~94.86)")

    if s.side != "LONG":
        logger.error(f"❌ SharkBreath side mismatch: expected LONG, got {s.side}")
        return False

    # 3. Test Scenario 2: SHORT Shark Breath at VAH
    logger.info("📡 Testing Scenario: SHORT Shark Breath at VAH")
    engine.dispatched_events = []  # Clear
    setup_engine.last_fire_ts[symbol] = 0  # Reset cooldown

    # Inject Microstructure (Price at VAH)
    micro = MicrostructureEvent(
        type=EventType.MICROSTRUCTURE, timestamp=2000.0, symbol=symbol, cvd=-100.0, skewness=-0.1, price=104.95
    )
    setup_engine.micro_memory[symbol].append((2000.0, 2000.0, micro))

    spike_event = SignalEvent(
        type=EventType.SIGNAL,
        timestamp=2000.0,
        symbol=symbol,
        side="TACTICAL",
        sensor_id="VolatilitySpike",
        score=1.0,
        metadata={"type": "VOLATILITY_SPIKE", "ratio": 4.1, "timestamp": 2000.0},
    )

    await setup_engine.on_signal(spike_event)

    signals = engine.dispatched_events
    shark_signals = [s for s in signals if s.metadata.get("trigger") == "SharkBreath"]

    if not shark_signals:
        logger.error("❌ SharkBreath signal NOT detected at VAH!")
        return False

    s = shark_signals[0]
    logger.info(f"✅ SharkBreath SHORT detected! Side: {s.side}")
    logger.info(f"   TP: {s.metadata['tp_price']} (Target: POC 100.0)")
    logger.info(f"   SL: {s.metadata['sl_price']} (Target: ~105.15)")

    if s.side != "SHORT":
        logger.error(f"❌ SharkBreath side mismatch: expected SHORT, got {s.side}")
        return False

    logger.info("🎉 All Shark Breath math scenarios PASSED!")
    return True


if __name__ == "__main__":
    asyncio.run(run_validator())
