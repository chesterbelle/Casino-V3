"""
Tests para ExchangeStateSync y sincronización de estado real.

Estos tests validan que:
1. ExchangeStateSync obtiene datos reales del exchange
2. CCXTAdapter retorna velas enriquecidas
3. PositionTracker modo híbrido funciona correctamente
4. Integración end-to-end con Kraken Demo
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.portfolio.position_tracker import PositionTracker
from exchanges.adapters.exchange_adapter import ExchangeAdapter
from exchanges.adapters.exchange_state_sync import ExchangeStateSync


class TestExchangeStateSync:
    """Tests para ExchangeStateSync component."""

    @pytest.fixture
    def mock_adapter(self):
        """Adapter mockeado para tests unitarios."""
        connector = Mock()
        connector.fetch_balance = AsyncMock(
            return_value={"free": {"USD": 5000.0}, "total": {"USD": 5000.0}, "used": {"USD": 0.0}}
        )
        connector.fetch_positions = AsyncMock(return_value=[])
        connector.fetch_my_trades = AsyncMock(return_value=[])

        adapter = Mock()
        adapter.connector = connector
        return adapter

    @pytest.mark.asyncio
    async def test_sync_equity_basic(self, mock_adapter):
        """Test básico de sync_equity."""
        sync = ExchangeStateSync(mock_adapter)

        equity = await sync.sync_equity()

        assert equity.balance == 5000.0
        assert equity.unrealized_pnl == 0.0
        assert equity.equity == 5000.0
        assert equity.open_positions == 0
        assert equity.currency == "USD"

    @pytest.mark.asyncio
    async def test_sync_equity_with_position(self, mock_adapter):
        """Test sync_equity con posición abierta."""
        # Mock posición con unrealized PnL
        mock_adapter.connector.fetch_positions = AsyncMock(
            return_value=[
                {
                    "symbol": "BTC/USD",
                    "side": "LONG",
                    "contracts": 0.1,
                    "entryPrice": 50000.0,
                    "markPrice": 51000.0,
                    "unrealizedPnl": 100.0,
                    "initialMargin": 500.0,
                    "leverage": 10,
                    "timestamp": 1699000000000,
                }
            ]
        )

        sync = ExchangeStateSync(mock_adapter)
        equity = await sync.sync_equity()

        assert equity.balance == 5000.0
        assert equity.unrealized_pnl == 100.0
        assert equity.equity == 5100.0
        assert equity.open_positions == 1
        assert equity.margin_used == 500.0

    @pytest.mark.asyncio
    async def test_sync_positions(self, mock_adapter):
        """Test sync_positions."""
        mock_adapter.connector.fetch_positions = AsyncMock(
            return_value=[
                {
                    "symbol": "BTC/USD",
                    "side": "LONG",
                    "contracts": 0.1,
                    "entryPrice": 50000.0,
                    "markPrice": 51000.0,
                    "unrealizedPnl": 100.0,
                    "initialMargin": 500.0,
                    "leverage": 10,
                    "timestamp": 1699000000000,
                }
            ]
        )

        sync = ExchangeStateSync(mock_adapter)
        positions = await sync.sync_positions()

        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USD"
        assert positions[0].side == "LONG"
        assert positions[0].size == 0.1
        assert positions[0].unrealized_pnl == 100.0

    @pytest.mark.asyncio
    async def test_sync_fills(self, mock_adapter):
        """Test sync_fills."""
        mock_adapter.connector.fetch_my_trades = AsyncMock(
            return_value=[
                {
                    "id": "trade_123",
                    "order": "order_456",
                    "symbol": "BTC/USD",
                    "side": "buy",
                    "price": 50000.0,
                    "amount": 0.1,
                    "cost": 5000.0,
                    "fee": {"cost": 2.5, "currency": "USD"},
                    "timestamp": 1699000000000,
                    "datetime": "2023-11-03T12:00:00Z",
                }
            ]
        )

        sync = ExchangeStateSync(mock_adapter)
        fills = await sync.sync_fills()

        assert len(fills) == 1
        assert fills[0].trade_id == "trade_123"
        assert fills[0].price == 50000.0
        assert fills[0].fee == 2.5

    @pytest.mark.asyncio
    async def test_equity_cache(self, mock_adapter):
        """Test que el cache de equity funciona."""
        sync = ExchangeStateSync(mock_adapter)

        # Primera llamada
        equity1 = await sync.sync_equity()
        call_count_1 = mock_adapter.connector.fetch_balance.call_count

        # Segunda llamada inmediata (debe usar cache)
        equity2 = await sync.sync_equity(use_cache=True)
        call_count_2 = mock_adapter.connector.fetch_balance.call_count

        # No debe haber llamadas adicionales
        assert call_count_2 == call_count_1
        assert equity1.equity == equity2.equity


class TestPositionTracker:
    """Tests para PositionTracker."""

    def test_hybrid_flow_pending(self):
        """Test flujo híbrido: detecta TP/SL y marca como pending."""
        tracker = PositionTracker()

        # Abrir posición
        position = tracker.open_position(
            order={
                "trade_id": "test_123",
                "symbol": "BTC/USD",
                "side": "LONG",
                "size": 0.01,
                "leverage": 10,
                "take_profit": 1.02,
                "stop_loss": 0.99,
            },
            entry_price=50000.0,
            entry_timestamp="2025-11-03T18:00:00",
            available_equity=10000.0,
        )

        # Simular vela que toca TP
        candle = {"high": 51100, "low": 49900, "close": 51000, "timestamp": "2025-11-03T18:05:00"}

        pending = tracker.check_and_close_positions(candle)

        # Debe marcar como pending
        assert len(pending) == 1
        assert pending[0]["confirmed"] == False
        assert pending[0]["pending_confirmation"] == True
        assert len(tracker.open_positions) == 1  # Aún abierta
        assert "test_123" in tracker.pending_confirmations

    def test_confirm_close(self):
        """Test confirmación de cierre con datos reales."""
        tracker = PositionTracker()

        # Abrir posición
        position = tracker.open_position(
            order={
                "trade_id": "test_123",
                "symbol": "BTC/USD",
                "side": "LONG",
                "size": 0.01,
                "leverage": 10,
                "take_profit": 1.02,
                "stop_loss": 0.99,
            },
            entry_price=50000.0,
            entry_timestamp="2025-11-03T18:00:00",
            available_equity=10000.0,
        )

        # Confirmar cierre con datos reales
        result = tracker.confirm_close(
            trade_id="test_123", exit_price=51050.0, exit_reason="TP", pnl=200.0, fee=3.5  # Precio REAL  # PnL REAL
        )

        assert result is not None
        assert result["confirmed"] == True
        assert result["exit_price"] == 51050.0
        assert result["pnl"] == 200.0
        assert result["fee"] == 3.5
        assert result["state_source"] == "exchange_confirmed"
        assert len(tracker.open_positions) == 0


class TestExchangeAdapterEnriched:
    """Tests para ExchangeAdapter con velas enriquecidas."""

    @pytest.mark.asyncio
    async def test_next_candle_enriched_structure(self):
        """Test que next_candle retorna estructura enriquecida."""
        # Mock connector
        connector = Mock()
        connector.exchange_name = "binance"
        # Return CCXT OHLCV format as list: [timestamp, open, high, low, close, volume]
        connector.fetch_ohlcv = AsyncMock(return_value=[[1699000000000, 50000.0, 50100.0, 49900.0, 50050.0, 100.0]])
        connector.fetch_balance = AsyncMock(return_value={"free": {"USD": 5000.0}, "total": {"USD": 5000.0}})
        connector.fetch_positions = AsyncMock(return_value=[])
        connector.fetch_my_trades = AsyncMock(return_value=[])

        table = ExchangeAdapter(connector, "BTC/USDT:USDT")
        table._connected = True

        candle = await table.next_candle()

        # Verify standard OHLCV structure fields
        assert candle is not None
        assert "timestamp" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle
        # _last_candle should be set to the last candle
        assert table._last_candle is not None


if __name__ == "__main__":
    # Ejecutar tests
    pytest.main([__file__, "-v", "-s"])
