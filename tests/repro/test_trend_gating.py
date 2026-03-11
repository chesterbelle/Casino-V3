import asyncio
import logging
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

# Mock config before imports that use it
import config.trading as config

config.OTF_STRICT_LOCK = True
config.VA_EXPANSION_GATING = True

from core.events import AggregatedSignalEvent, EventType, SignalEvent
from decision.aggregator import SignalAggregatorV3

logging.basicConfig(level=logging.INFO)


class TestTrendGating(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = MagicMock()
        self.engine.dispatch = AsyncMock()

        self.context_registry = MagicMock()
        # default neutral
        self.context_registry.otf = {}
        self.context_registry.get_regime.return_value = "NORMAL"
        self.context_registry.get_structural.return_value = (0, 0, 0)
        self.context_registry.get_pulse.return_value = {"speed": 2.0}
        self.context_registry.get_gravity.return_value = {"btc_delta": 0, "btc_trend": "NEUTRAL"}

        self.aggregator = SignalAggregatorV3(self.engine, context_registry=self.context_registry)
        self.symbol = "ETHUSDT"
        self.ts = 123456789.0
        self.aggregator.latest_candle_ts[self.symbol] = self.ts
        self.aggregator.latest_candle_open[self.symbol] = 2000.0
        self.aggregator.latest_candle_close[self.symbol] = 2010.0  # Moving UP

    async def test_otf_lock_rejects_short_in_bull_otf(self):
        # Setup: BULL_OTF
        self.context_registry.otf[self.symbol] = "BULL_OTF"

        # Signal: High-conviction SHORT
        signal = SignalEvent(
            type=EventType.SIGNAL,
            timestamp=time.time(),
            symbol=self.symbol,
            side="SHORT",
            sensor_id="FootprintStackedImbalance",
            score=0.9,  # High score
            metadata={"fast_track": True, "setup_type": "continuation", "price": 2010.0},
        )

        await self.aggregator.on_signal(signal)
        await asyncio.sleep(0.1)  # Wait for fast-track task

        # Verify: Aggregated signal should be SKIP
        # Check calls to engine.dispatch
        args = self.engine.dispatch.call_args_list
        found_skip = False
        for call in args:
            event = call[0][0]
            if isinstance(event, AggregatedSignalEvent) and event.side == "SKIP":
                found_skip = True
                reason = event.metadata.get("rejection_reason", "Gated") if event.metadata else "Gated (No Metadata)"
                print(f"✅ Success: Signal rejected as expected. Reason: {reason}")

        self.assertTrue(found_skip, "Aggregator should have emitted a SKIP event")

    async def test_va_expansion_rejects_short(self):
        # Setup: NEUTRAL OTF but price > VAH and price > Open
        self.context_registry.otf[self.symbol] = "NEUTRAL"
        self.context_registry.get_structural.return_value = (2000.0, 2005.0, 1995.0)  # VAH=2005
        # Open=2000, Close=2010 (already set in asyncSetUp)

        # Signal: High-conviction SHORT
        signal = SignalEvent(
            type=EventType.SIGNAL,
            timestamp=time.time(),
            symbol=self.symbol,
            side="SHORT",
            sensor_id="FootprintStackedImbalance",
            score=0.9,
            metadata={"fast_track": True, "setup_type": "continuation", "price": 2010.0},
        )

        await self.aggregator.on_signal(signal)
        await asyncio.sleep(0.1)

        found_skip = False
        for call in self.engine.dispatch.call_args_list:
            event = call[0][0]
            if isinstance(event, AggregatedSignalEvent) and event.side == "SKIP":
                found_skip = True

        self.assertTrue(found_skip, "Aggregator should have rejected SHORT during VA expansion UP")


if __name__ == "__main__":
    unittest.main()
