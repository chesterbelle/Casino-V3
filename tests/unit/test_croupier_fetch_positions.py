from types import SimpleNamespace

import pytest


class FakeStateSync:
    def __init__(self, to_return=None, raise_exc=False):
        self.to_return = to_return
        self.raise_exc = raise_exc

    async def sync_positions(self):
        if self.raise_exc:
            raise Exception("sync failed")
        return self.to_return


class FakeConnector:
    def __init__(self, positions):
        self._positions = positions

    async def fetch_positions(self, symbols=None):
        return self._positions


class MinimalCroupierLike:
    def __init__(self, state_sync, connector):
        self.state_sync = state_sync
        self.exchange_adapter = SimpleNamespace(connector=connector)

    async def _fetch_positions(self, symbols: list = None):
        try:
            synced = await self.state_sync.sync_positions()
            if symbols:
                syms = set(symbols)
                return [p for p in synced if getattr(p, "symbol", None) in syms]
            return synced
        except Exception:
            return await self.exchange_adapter.connector.fetch_positions(symbols)


@pytest.mark.asyncio
async def test_fetch_positions_prefers_sync():
    fake_positions = [SimpleNamespace(symbol="BTC/USD", size=1)]
    state_sync = FakeStateSync(to_return=fake_positions)
    connector = FakeConnector(positions=[{"symbol": "X"}])
    c = MinimalCroupierLike(state_sync, connector)

    res = await c._fetch_positions(["BTC/USD"])

    assert isinstance(res, list)
    assert getattr(res[0], "symbol", None) == "BTC/USD"


@pytest.mark.asyncio
async def test_fetch_positions_fallback_to_connector():
    state_sync = FakeStateSync(raise_exc=True)
    connector_positions = [{"symbol": "ETH/USD", "contracts": 2}]
    connector = FakeConnector(connector_positions)
    c = MinimalCroupierLike(state_sync, connector)

    res = await c._fetch_positions()

    assert res == connector_positions
