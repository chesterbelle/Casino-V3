from core.portfolio.balance_manager import BalanceManager


def test_balance_manager_apply_and_get():
    bm = BalanceManager(starting_balance=1000.0)
    assert bm.get_balance() == 1000.0
    assert bm.get_equity() == 1000.0

    bm.apply_trade_result(pnl=50.0, fee=1.0)
    assert bm.get_balance() == 1049.0
    assert bm.get_equity() == 1049.0

    bm.update_balance(-49.0)
    assert bm.get_balance() == 1000.0
    assert bm.can_open_position(1000.0) is True
    assert bm.can_open_position(1000.1) is False

    state = bm.get_state()
    assert state["balance"] == 1000.0
    assert state["equity"] == 1000.0
    assert state["trades"] == 1
