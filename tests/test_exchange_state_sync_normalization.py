import pytest

from exchanges.adapters.exchange_state_sync import ExchangeStateSync, Position


class FakeConnector:
    async def fetch_positions(self, symbols=None):
        # Return a mix of dict and object representations to validate normalization
        return [
            {
                "symbol": "TEST/USDT",
                "side": "long",
                "contracts": 2.0,
                "entryPrice": 100.0,
                "markPrice": 100.5,
                "unrealizedPnl": 1.0,
                "initialMargin": 10.0,
                "leverage": 1,
                "timestamp": 123,
            }
        ]


@pytest.mark.asyncio
async def test_sync_positions_returns_dataclass_positions():
    connector = FakeConnector()
    sync = ExchangeStateSync(connector)

    positions = await sync.sync_positions()
    assert isinstance(positions, list)
    assert len(positions) == 1
    pos = positions[0]
    assert isinstance(pos, Position)
    assert pos.symbol == "TEST/USDT"
    assert pos.size == 2.0
    assert pos.entry_price == 100.0
    assert pos.mark_price == 100.5


def test_normalize_position_public_api():
    # ensure public normalize_position wraps internal logic
    connector = FakeConnector()
    sync = ExchangeStateSync(connector)
    raw = {
        "symbol": "TEST/USDT",
        "side": "long",
        "contracts": 3.0,
        "entryPrice": 110.0,
        "markPrice": 111.0,
        "unrealizedPnl": 1.0,
        "initialMargin": 10.0,
        "leverage": 1,
        "timestamp": 124,
    }
    pos = sync.normalize_position(raw)
    assert isinstance(pos, Position)
    assert pos.size == 3.0
    assert pos.entry_price == 110.0
