import pytest

from core.clock import Clock
from core.network import NetworkStatus
from exchanges.adapters.exchange_adapter import ExchangeAdapter
from exchanges.connectors.connector_base import BaseConnector


class MockConnector(BaseConnector):
    def __init__(self):
        self._connected = True
        self._name = "Mock"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def exchange_name(self) -> str:
        return self._name

    async def connect(self):
        pass

    async def close(self):
        pass

    async def fetch_ohlcv(self, symbol, timeframe, limit=100):
        return []

    async def fetch_balance(self):
        return {}

    async def fetch_positions(self, symbols=None):
        return []

    async def fetch_active_symbols(self):
        return []

    async def create_order(self, symbol, side, amount, price=None, order_type="market", params=None):
        return {}

    def normalize_symbol(self, s):
        return s

    def denormalize_symbol(self, s):
        return s


@pytest.mark.asyncio
async def test_adapter_lifecycle():
    connector = MockConnector()
    adapter = ExchangeAdapter(connector, symbol="BTC/USDT")

    # 1. Initial State
    assert adapter.network_status == NetworkStatus.STOPPED

    # 2. Start
    await adapter.start()
    assert adapter.network_status == NetworkStatus.CONNECTED

    # 3. Network Check via Tick
    # Tick with timestamp 100 (divisible by 5) -> Should trigger check
    connector._connected = False  # Simulate disconnect
    await adapter.tick(100.0)
    assert adapter.network_status == NetworkStatus.NOT_CONNECTED

    # 4. Reconnect
    connector._connected = True
    await adapter.tick(105.0)
    assert adapter.network_status == NetworkStatus.CONNECTED

    # 5. Stop
    await adapter.stop()
    assert adapter.network_status == NetworkStatus.STOPPED


@pytest.mark.asyncio
async def test_clock_integration():
    """Verify Adapter works inside a Clock."""
    connector = MockConnector()
    adapter = ExchangeAdapter(connector, symbol="BTC/USDT")
    clock = Clock(tick_size_seconds=0.1)

    clock.add_iterator(adapter)

    await clock.start()
    assert adapter.network_status == NetworkStatus.CONNECTED

    await clock.stop()
    assert adapter.network_status == NetworkStatus.STOPPED
