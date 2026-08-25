import pytest

from core.portfolio.portfolio_guard import GuardConfig, GuardState, PortfolioGuard


@pytest.fixture
def base_config():
    return GuardConfig(
        enabled=True,
        caution_drawdown_pct=0.05,
        critical_drawdown_pct=0.10,
        drawdown_window_minutes=30.0,
        max_consecutive_losses=7,
        max_errors_in_window=50,
        error_window_minutes=5.0,
        solvency_multiplier=1.25,
        min_notional=20.0,
        bet_size=0.01,
        caution_sizing_violations=3,
        terminal_sizing_violations=10,
        recovery_cooldown_seconds=60.0,
    )


@pytest.fixture
def guard(base_config):
    return PortfolioGuard(config=base_config)


def test_initial_state(guard):
    assert guard.state == GuardState.HEALTHY
    assert guard._sizing_violations == 0
    assert guard._consecutive_losses == 0


def test_loss_streak_to_critical(guard):
    # Initial state
    assert guard.state == GuardState.HEALTHY

    # Simulate 6 consecutive losses (config max is 7)
    for _ in range(6):
        guard.on_trade_closed(pnl=-1.0, exit_reason="SL")

    # Should still be healthy (or perhaps caution if we had rules for that, but here it's binary)
    assert guard.state == GuardState.HEALTHY

    # 7th loss should trigger CRITICAL
    guard.on_trade_closed(pnl=-1.0, exit_reason="SL")
    assert guard.state == GuardState.CRITICAL


def test_sizing_violations_escalation(guard):
    assert guard.state == GuardState.HEALTHY

    # Trigger CAUTION
    for _ in range(3):
        guard.on_sizing_violation("BTCUSDT", 15.0, 20.0)

    assert guard.state == GuardState.CAUTION

    # Trigger TERMINAL (10 violations)
    for _ in range(7):  # 7 more to reach 10
        guard.on_sizing_violation("BTCUSDT", 15.0, 20.0)

    assert guard.state == GuardState.TERMINAL


def test_drawdown_velocity(guard):
    # Set initial balance (peak) - Using 3000.0 to pass solvency check
    guard.on_balance_update(3000.0)
    assert guard.state == GuardState.HEALTHY

    # Drop by 6% (Caution Threshold is 5%)
    guard.on_balance_update(2820.0)
    assert guard.state == GuardState.CAUTION

    # Drop by 11% from peak (Critical Threshold is 10%)
    guard.on_balance_update(2670.0)
    assert guard.state == GuardState.CRITICAL


def test_error_rate_escalation(guard):
    # Trigger 50 errors
    for i in range(50):
        guard.on_execution_error("network_error", "BTCUSDT")

    assert guard.state == GuardState.TERMINAL


def test_solvency_check(guard):
    # equity * bet < min_notional * solvency_multiplier -> TERMINAL
    # config: min_notional=20, bet=0.01, mult=1.25 -> target = 25.0
    # equity * 0.01 < 25 -> equity < 2500 is technically insolvent if bet is fixed to %?
    # Actually, let's see how insolvency is defined:
    # `if equity * self.config.bet_size < self.config.min_notional * self.config.solvency_multiplier:`
    # For a balance of 1000, 1000 * 0.01 = 10. 10 < 20 * 1.25 (25). So 1000 is insolvent?
    # Yes, if bet_size is strictly 1%, then a 1000 balance gives $10 bet, which is < min_notional (20).
    # This should trigger TERMINAL.

    guard.on_balance_update(1000.0)
    assert guard.state == GuardState.TERMINAL


def test_hysteresis_cooldown(guard):
    # Trigger caution via drawdown - use 3000 to pass solvency
    guard.on_balance_update(3000.0)  # peak
    guard.on_balance_update(2820.0)  # caution (6% drop)

    assert guard.state == GuardState.CAUTION

    # Try to recover immediately (back to 3000)
    guard.on_balance_update(3000.0)

    # Due to hysteresis, it should still be CAUTION
    assert guard.state == GuardState.CAUTION

    # Simulate time pass (cooldown is 60s)
    # We can fake the last_state_change_ts
    guard._last_state_change_ts -= 61.0

    # Update balance again
    guard.on_balance_update(3000.0)

    # Now it should recover to HEALTHY
    assert guard.state == GuardState.HEALTHY


def test_daily_drawdown(guard):
    # Set initial balance at start of day (Using 3000.0 to pass solvency check)
    # The first balance update sets _daily_start_equity
    guard.on_balance_update(3000.0)
    assert guard._daily_start_equity == 3000.0
    assert guard.state == GuardState.HEALTHY

    # Drop by 15% (Max daily drawdown config default is 20%, but in tests it's 20% by default? Wait, I didn't add it to base_config fixture! Let's check config.)
    # Since base_config fixture doesn't explicitly set max_daily_drawdown_pct, it uses default 0.20
    guard.on_balance_update(2500.0)  # 16.6% drop
    # Since 16.6% > 10% (critical_drawdown_pct), it should hit CRITICAL due to velocity.
    assert guard.state == GuardState.CRITICAL

    # Drop by 21% (Max daily drawdown is 20%)
    guard.on_balance_update(2300.0)  # 3000 -> 2300 is a 23.3% drop
    assert guard.state == GuardState.TERMINAL


def test_kill_switch(guard, monkeypatch):
    import os

    # Mock os.path.exists to simulate emergency_stop.flag
    def mock_exists(path):
        if path == "emergency_stop.flag":
            return True
        return False

    monkeypatch.setattr(os.path, "exists", mock_exists)

    assert guard.state == GuardState.HEALTHY
    guard.check_kill_switch()
    assert guard.state == GuardState.TERMINAL
    assert guard._kill_switch_activated == True
