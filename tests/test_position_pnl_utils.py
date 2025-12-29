from core.portfolio.utils import calculate_position_pnl
from exchanges.adapters.exchange_state_sync import Position as ExPosition


def test_calculate_pnl_for_dict_position():
    position = {"symbol": "X", "side": "LONG", "amount": 2.0, "entry_price": 100.0, "notional": 200.0}
    pnl = calculate_position_pnl(position, exit_price=102.0, fee=0.5)
    expected = 200.0 * ((102.0 - 100.0) / 100.0) - 0.5
    assert abs(pnl - expected) < 1e-6


def test_calculate_pnl_for_dataclass_position():
    pos = ExPosition(
        symbol="X",
        side="LONG",
        size=2.0,
        entry_price=100.0,
        mark_price=100.0,
        unrealized_pnl=0.0,
        margin=0.0,
        leverage=1.0,
        liquidation_price=None,
        timestamp=1,
    )
    pnl = calculate_position_pnl(pos, exit_price=102.0, fee=0.5)
    expected = (pos.size * pos.entry_price) * ((102.0 - 100.0) / 100.0) - 0.5
    assert abs(pnl - expected) < 1e-6
