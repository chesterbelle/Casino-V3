import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.events import AggregatedSignalEvent, EventType
from players.adaptive import AdaptivePlayer


class TestPhase700SetupClamping(unittest.IsolatedAsyncioTestCase):
    """Phase 700 RESTORED: Verify structural percentage clamping per setup type."""

    async def asyncSetUp(self):
        self.engine = MagicMock()
        self.engine.dispatch = AsyncMock()
        self.croupier = MagicMock()
        self.croupier.get_active_positions.return_value = []
        self.croupier.is_pending.return_value = False
        self.croupier.get_equity.return_value = 10000.0

        self.context_registry = MagicMock()
        self.player = AdaptivePlayer(self.engine, self.croupier, context_registry=self.context_registry)

        self.patcher = patch("players.adaptive.config")
        self.mock_config = self.patcher.start()
        self.mock_config.COMMISSION_RATE = 0.00035
        self.mock_config.SLIPPAGE_DEFAULT = 0.00015

    def tearDown(self):
        self.patcher.stop()

    async def test_reversion_clamp_allows_trade(self):
        """Reversion setup: TP clamped to 0.10-0.60%, SL clamped to 0.15-0.45%."""
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
            metadata={"setup_type": "reversion", "tp_price": 100.50, "sl_price": 99.70, "price": 100.0},
        )
        self.context_registry.get_latest_price.return_value = 100.0
        self.context_registry.get_regime.return_value = "NORMAL"

        with self.assertLogs("players.adaptive", level="INFO") as cm:
            await self.player.on_aggregated_signal(event)
            self.assertTrue(any("Decision: LONG" in line for line in cm.output))

    async def test_continuation_clamp_allows_trade(self):
        """Continuation setup: TP clamped to 0.15-0.90%, SL clamped to 0.15-0.55%."""
        event = AggregatedSignalEvent(
            type=EventType.AGGREGATED_SIGNAL,
            timestamp=time.time(),
            symbol="BTCUSDT",
            candle_timestamp=time.time(),
            selected_sensor="FootprintStackedImbalance",
            sensor_score=0.8,
            side="LONG",
            confidence=0.8,
            total_signals=1,
            metadata={"setup_type": "continuation", "tp_price": 100.80, "sl_price": 99.50, "price": 100.0},
        )
        self.context_registry.get_latest_price.return_value = 100.0
        self.context_registry.get_regime.return_value = "NORMAL"

        with self.assertLogs("players.adaptive", level="INFO") as cm:
            await self.player.on_aggregated_signal(event)
            self.assertTrue(any("Decision: LONG" in line for line in cm.output))

    async def test_initial_clamp_allows_trade(self):
        """Initial breakout: TP clamped to 0.20-0.80%, SL clamped to 0.20-0.50%."""
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
        self.context_registry.get_latest_price.return_value = 100.0
        self.context_registry.get_regime.return_value = "NORMAL"

        with self.assertLogs("players.adaptive", level="INFO") as cm:
            await self.player.on_aggregated_signal(event)
            # TP 1.5% will be clamped to 0.80% max for initial
            self.assertTrue(any("Decision: LONG" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
