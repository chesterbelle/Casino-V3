import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.events import AggregatedSignalEvent, EventType
from players.adaptive import AdaptivePlayer


class TestDynamicRR(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = MagicMock()
        self.engine.dispatch = AsyncMock()
        self.croupier = MagicMock()
        self.croupier.get_active_positions.return_value = []
        self.croupier.is_pending.return_value = False
        self.croupier.get_equity.return_value = 10000.0

        self.context_registry = MagicMock()
        self.player = AdaptivePlayer(self.engine, self.croupier, context_registry=self.context_registry)

        # Mocking config for precise RR control
        self.patcher = patch("players.adaptive.config")
        self.mock_config = self.patcher.start()
        self.mock_config.SETUP_RR_RATIOS = {
            "FootprintTrappedTraders": 1.2,
            "FootprintDeltaDivergence": 2.0,
            "FootprintStackedImbalance": 1.5,
            "DEFAULT": 1.1,
        }
        self.mock_config.MIN_TP_PROXIMITY = 0.0005
        self.mock_config.MIN_DISTANCE_PCT = 0.0001
        self.mock_config.MAX_DISTANCE_PCT = 0.05
        self.mock_config.ATR_SL_MULT = 1.2
        self.mock_config.COMMISSION_RATE = 0.00035
        self.mock_config.SLIPPAGE_DEFAULT = 0.00015
        self.mock_config.MAX_POSITION_SIZE = 0.02

    def tearDown(self):
        self.patcher.stop()

    async def test_trapped_traders_rr_pass(self):
        """1.2 RR should PASS for Trapped Traders."""
        event = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=time.time(),
            symbol="BTCUSDT",
            candle_timestamp=time.time(),
            selected_sensor="FootprintTrappedTraders",
            sensor_score=0.8,
            side="LONG",
            confidence=0.8,
            total_signals=1,
            metadata={"setup_type": "initial", "tp_price": 101.2, "sl_price": 99.0, "price": 100.0},
        )
        # Entry 100.0 (from metadata), TP 101.2 (dist 1.2), SL 99.0 (dist 1.0) -> RR 1.2
        self.context_registry.get_latest_price.return_value = 100.0
        self.context_registry.get_regime.return_value = "NORMAL"

        with self.assertLogs("players.adaptive", level="INFO") as cm:
            await self.player.on_aggregated_signal(event)
            # Check if decision was emitted (meaning it passed gating)
            self.assertTrue(any("Decision: LONG" in line for line in cm.output))

    async def test_delta_divergence_rr_pass_due_to_scalp_override(self):
        """1.5 RR should PASS now for Delta Divergence because of scalper override (0.75)."""
        event = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=time.time(),
            symbol="BTCUSDT",
            candle_timestamp=time.time(),
            selected_sensor="FootprintDeltaDivergence",
            sensor_score=0.8,
            side="LONG",
            confidence=0.8,
            total_signals=1,
            metadata={"setup_type": "initial", "tp_price": 101.5, "sl_price": 99.0, "price": 100.0},
        )
        # Entry 100.0, TP 101.5 (dist 1.5), SL 99.0 (dist 1.0) -> RR 1.5
        self.context_registry.get_latest_price.return_value = 100.0
        self.context_registry.get_regime.return_value = "NORMAL"

        with self.assertLogs("players.adaptive", level="INFO") as cm:
            await self.player.on_aggregated_signal(event)
            self.assertTrue(any("Decision: LONG" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
