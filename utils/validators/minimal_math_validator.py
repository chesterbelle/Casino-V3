import asyncio
import logging
import os
import sys
import time

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath("."))

from core.events import EventType
from decision.aggregator import AggregatedSignalEvent
from players.adaptive import AdaptivePlayer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("MinimalValidator")


class MockEngine:
    def subscribe(self, event_type, handler):
        pass

    async def dispatch(self, event):
        pass


class MockCroupier:
    def get_active_positions(self):
        return []

    def get_equity(self):
        return 1000.0

    def is_pending(self, symbol):
        return False


async def run_minimal():
    logger.info("Starting Minimal Math Validator...")
    player = AdaptivePlayer(MockEngine(), MockCroupier())

    scenarios = [
        {
            "name": "SHORT Reversion",
            "side": "SHORT",
            "metadata": {
                "setup_type": "reversion",
                "price": 100.0,
                "1h_poc": 95.0,
                "1h_vah": 105.0,
                "1h_val": 90.0,
            },
        },
        {
            "name": "LONG Reversion",
            "side": "LONG",
            "metadata": {
                "setup_type": "reversion",
                "price": 90.0,
                "1h_poc": 95.0,
                "1h_vah": 100.0,
                "1h_val": 85.0,
            },
        },
    ]

    for s in scenarios:
        logger.info(f"Testing {s['name']}...")
        event = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=time.time(),
            symbol="BTCUSDT",
            candle_timestamp=time.time(),
            selected_sensor="TestSensor",
            sensor_score=1.0,
            side=s["side"],
            confidence=1.0,
            total_signals=1,
            metadata=s["metadata"],
        )
        await player.on_aggregated_signal(event)
        logger.info(f"✅ {s['name']} processed.")


if __name__ == "__main__":
    asyncio.run(run_minimal())
