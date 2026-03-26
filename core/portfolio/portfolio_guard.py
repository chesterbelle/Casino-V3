"""
🛡️ PortfolioGuard — Event-Driven Portfolio Health Monitor
==========================================================

Monitors portfolio health via callbacks from existing components:
- BalanceManager  → drawdown velocity detection
- PositionTracker → loss streak tracking
- ErrorHandler    → execution error rate
- OrderExecutor   → sizing violations (min_notional)

State Machine:
    HEALTHY → CAUTION → CRITICAL → TERMINAL

Each state triggers a graduated response:
    CAUTION  → Block new entries
    CRITICAL → Activate drain mode
    TERMINAL → Emergency shutdown signal

Zero latency: purely event-driven, no polling or timers.

Author: Casino V3 Team
Phase: 249
"""

import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("PortfolioGuard")


class GuardState(IntEnum):
    """Portfolio health states (ordered by severity)."""

    HEALTHY = 0
    CAUTION = 1
    CRITICAL = 2
    TERMINAL = 3


@dataclass
class GuardConfig:
    """Configurable thresholds for PortfolioGuard."""

    enabled: bool = True

    # Drawdown velocity (rolling window)
    caution_drawdown_pct: float = 0.05  # 5% loss in window → CAUTION
    critical_drawdown_pct: float = 0.10  # 10% loss in window → CRITICAL
    drawdown_window_minutes: float = 30.0  # Rolling window size

    # Loss streak
    max_consecutive_losses: int = 7  # → CRITICAL (raised for backtest stability)

    # Error rate
    max_errors_in_window: int = 50  # Increased for backtest stability (Phase 310)
    error_window_minutes: float = 5.0

    # Solvency
    solvency_multiplier: float = 1.25  # equity * bet >= min_notional * multiplier
    min_notional: float = 20.0  # Default Binance Futures
    bet_size: float = 0.01  # Default 1%

    # Sizing violations
    caution_sizing_violations: int = 3  # → CAUTION after N violations
    terminal_sizing_violations: int = 10  # → TERMINAL after N violations

    # Hysteresis: minimum time in elevated state before allowing recovery
    recovery_cooldown_seconds: float = 60.0  # 1 minute (reduced to avoid backtest lockout)


@dataclass
class _BalanceSnapshot:
    """Single balance observation."""

    timestamp: float
    equity: float


@dataclass
class _TradeResult:
    """Single trade outcome."""

    timestamp: float
    pnl: float
    exit_reason: str


@dataclass
class _ErrorEvent:
    """Single execution error observation."""

    timestamp: float
    error_type: str
    symbol: str


class PortfolioGuard:
    """
    Event-driven portfolio health monitor.

    Consumes events from BalanceManager, PositionTracker, ErrorHandler,
    and OrderExecutor. Determines portfolio health state and notifies
    listeners via callbacks.

    Usage:
        guard = PortfolioGuard(config)
        guard.add_state_listener(my_callback)

        # These are called by existing components:
        guard.on_balance_update(1500.0)
        guard.on_trade_closed(-5.0, "SL")
        guard.on_execution_error("order_not_found", "LTCUSDT")
        guard.on_sizing_violation("LTCUSDT", 17.0, 20.0)
    """

    def __init__(self, config: Optional[GuardConfig] = None):
        self.config = config or GuardConfig()
        self.state = GuardState.HEALTHY
        self._last_state_change_ts: float = 0.0

        # Rolling windows (bounded, O(1) append)
        self._balance_history: Deque[_BalanceSnapshot] = deque(maxlen=720)  # ~12h at 1/min
        self._trade_results: Deque[_TradeResult] = deque(maxlen=200)
        self._error_log: Deque[_ErrorEvent] = deque(maxlen=100)

        # Counters
        self._sizing_violations: int = 0
        self._consecutive_losses: int = 0
        self._session_peak_equity: float = 0.0

        # State change listeners: callback(old_state, new_state, reason)
        self._state_listeners: List[Callable[[GuardState, GuardState, str], None]] = []

        # Stats for observability
        self._stats: Dict[str, int] = {
            "total_balance_updates": 0,
            "total_trades_processed": 0,
            "total_errors_received": 0,
            "total_sizing_violations": 0,
            "state_transitions": 0,
        }

        logger.info(
            f"🛡️ PortfolioGuard initialized | Enabled: {self.config.enabled} | "
            f"Drawdown: {self.config.caution_drawdown_pct:.0%}/{self.config.critical_drawdown_pct:.0%} | "
            f"Max Losses: {self.config.max_consecutive_losses} | "
            f"Error Cap: {self.config.max_errors_in_window}/{self.config.error_window_minutes:.0f}min"
        )

    # =========================================================
    # LISTENER MANAGEMENT
    # =========================================================

    def add_state_listener(self, callback: Callable[[GuardState, GuardState, str], None]) -> None:
        """Register a callback for state changes: callback(old_state, new_state, reason)."""
        if callback not in self._state_listeners:
            self._state_listeners.append(callback)

    def remove_state_listener(self, callback: Callable) -> None:
        """Unregister a state change callback."""
        if callback in self._state_listeners:
            self._state_listeners.remove(callback)

    # =========================================================
    # EVENT RECEIVERS (called by existing components)
    # =========================================================

    def on_balance_update(self, equity: float, timestamp: Optional[float] = None) -> None:
        """
        Called by BalanceManager on every real-time balance update.
        Tracks equity history and checks drawdown velocity.
        """
        if not self.config.enabled:
            return

        now = timestamp if timestamp is not None else time.time()
        self._stats["total_balance_updates"] += 1

        # Track peak
        if equity > self._session_peak_equity:
            self._session_peak_equity = equity

        self._balance_history.append(_BalanceSnapshot(timestamp=now, equity=equity))

        # Run checks
        self._evaluate_state(now)

    def on_trade_closed(self, pnl: float, exit_reason: str, timestamp: Optional[float] = None) -> None:
        """
        Called when a position closes (via PositionTracker close listener).
        Tracks consecutive losses and PnL trajectory.
        """
        if not self.config.enabled:
            return

        now = timestamp if timestamp is not None else time.time()
        self._stats["total_trades_processed"] += 1

        self._trade_results.append(_TradeResult(timestamp=now, pnl=pnl, exit_reason=exit_reason))

        # Update consecutive loss counter
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        # Run checks
        self._evaluate_state(now)

    def on_execution_error(self, error_type: str, symbol: str = "UNKNOWN", timestamp: Optional[float] = None) -> None:
        """
        Called by ErrorHandler on non-retriable execution errors.
        Tracks error rate for anomaly detection.
        """
        if not self.config.enabled:
            return

        now = timestamp if timestamp is not None else time.time()
        self._stats["total_errors_received"] += 1

        self._error_log.append(_ErrorEvent(timestamp=now, error_type=error_type, symbol=symbol))

        # Run checks
        self._evaluate_state(now)

    def on_sizing_violation(
        self, symbol: str, notional: float, min_required: float, timestamp: Optional[float] = None
    ) -> None:
        """
        Called by OrderExecutor when order notional < min_notional.
        Strong signal that balance is too low to trade.
        """
        if not self.config.enabled:
            return

        now = timestamp if timestamp is not None else time.time()
        self._sizing_violations += 1
        self._stats["total_sizing_violations"] += 1

        logger.warning(
            f"🛡️ GUARD: Sizing violation #{self._sizing_violations} | "
            f"{symbol}: ${notional:.2f} < ${min_required:.2f}"
        )

        # Run checks
        self._evaluate_state(now)

    # =========================================================
    # RISK EVALUATION ENGINE
    # =========================================================

    def _evaluate_state(self, timestamp: Optional[float] = None) -> None:
        """
        Central evaluation: runs all risk checks and determines
        the highest severity state among them.
        """
        now = timestamp if timestamp is not None else time.time()
        checks = [
            self._check_solvency(),
            self._check_drawdown_velocity(now),
            self._check_loss_streak(now),
            self._check_error_rate(now),
            self._check_sizing_violations(),
        ]

        # Take the worst (highest) state from all checks
        worst_state = GuardState.HEALTHY
        worst_reason = ""

        for check_state, check_reason in checks:
            if check_state is not None and check_state > worst_state:
                worst_state = check_state
                worst_reason = check_reason

        # Only transition UP (escalate), not down — recovery requires explicit cooldown
        if worst_state > self.state:
            self._transition_to(worst_state, worst_reason, now)
        elif worst_state < self.state:
            # Check if recovery is allowed (hysteresis)
            elapsed = now - self._last_state_change_ts
            if elapsed >= self.config.recovery_cooldown_seconds:
                if worst_state == GuardState.HEALTHY:
                    # Reset streak counter so recovery is clean
                    self._consecutive_losses = 0
                    logger.info("🔄 GUARD: Consecutive loss streak reset on HEALTHY recovery")
                self._transition_to(worst_state, f"Recovery after {elapsed:.0f}s cooldown", now)

    def _check_solvency(self) -> Tuple[Optional[GuardState], str]:
        """
        Check if balance is sufficient to produce valid orders.
        equity * bet_size >= min_notional * solvency_multiplier
        """
        if not self._balance_history:
            return (None, "")

        current_equity = self._balance_history[-1].equity
        min_viable = self.config.min_notional * self.config.solvency_multiplier / self.config.bet_size

        if current_equity < min_viable:
            return (
                GuardState.TERMINAL,
                f"Insolvent: equity ${current_equity:.2f} < "
                f"min viable ${min_viable:.2f} (${self.config.min_notional} × "
                f"{self.config.solvency_multiplier} / {self.config.bet_size:.2%})",
            )

        return (None, "")

    def _check_drawdown_velocity(self, now: float) -> Tuple[Optional[GuardState], str]:
        """
        Check rate of equity loss within the rolling window.
        Uses peak equity within the window as reference.
        """
        if len(self._balance_history) < 2:
            return (None, "")

        window_start = now - (self.config.drawdown_window_minutes * 60)

        # Find peak equity within the window
        peak_in_window = 0.0
        for snap in self._balance_history:
            if snap.timestamp >= window_start and snap.equity > peak_in_window:
                peak_in_window = snap.equity

        if peak_in_window <= 0:
            return (None, "")

        current_equity = self._balance_history[-1].equity
        drawdown_pct = (peak_in_window - current_equity) / peak_in_window

        if drawdown_pct >= self.config.critical_drawdown_pct:
            return (
                GuardState.CRITICAL,
                f"Drawdown {drawdown_pct:.1%} in {self.config.drawdown_window_minutes:.0f}min "
                f"(peak ${peak_in_window:.2f} → ${current_equity:.2f})",
            )

        if drawdown_pct >= self.config.caution_drawdown_pct:
            return (
                GuardState.CAUTION,
                f"Drawdown {drawdown_pct:.1%} in {self.config.drawdown_window_minutes:.0f}min "
                f"(peak ${peak_in_window:.2f} → ${current_equity:.2f})",
            )

        return (None, "")

    def _check_loss_streak(self, now: float) -> Tuple[Optional[GuardState], str]:
        """
        Check consecutive losses.
        If we are already in CRITICAL/CAUTION due to losses, and the cooldown has elapsed,
        we shouldn't KEEP returning CRITICAL, or else we can never recover.
        """
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            # Check if cooldown has elapsed. If so, return None so recovery can happen
            if self.state >= GuardState.CAUTION:
                elapsed = now - self._last_state_change_ts
                if elapsed >= self.config.recovery_cooldown_seconds:
                    return (None, "")

            return (
                GuardState.CRITICAL,
                f"{self._consecutive_losses} consecutive losses (Max: {self.config.max_consecutive_losses})",
            )
        return (None, "")

    def _check_error_rate(self, now: float) -> Tuple[Optional[GuardState], str]:
        """Check execution error rate within the window."""
        if not self._error_log:
            return (None, "")

        window_start = now - (self.config.error_window_minutes * 60)

        recent_errors = sum(1 for e in self._error_log if e.timestamp >= window_start)

        if recent_errors >= self.config.max_errors_in_window:
            return (
                GuardState.TERMINAL,
                f"Error storm: {recent_errors} errors in " f"{self.config.error_window_minutes:.0f}min",
            )

        return (None, "")

    def _check_sizing_violations(self) -> Tuple[Optional[GuardState], str]:
        """Check accumulated sizing violations."""
        if self._sizing_violations >= self.config.terminal_sizing_violations:
            return (
                GuardState.TERMINAL,
                f"Sizing violations: {self._sizing_violations} "
                f"(threshold: {self.config.terminal_sizing_violations})",
            )

        if self._sizing_violations >= self.config.caution_sizing_violations:
            return (
                GuardState.CAUTION,
                f"Sizing violations: {self._sizing_violations} "
                f"(threshold: {self.config.caution_sizing_violations})",
            )

        return (None, "")

    # =========================================================
    # STATE MANAGEMENT
    # =========================================================

    def _transition_to(self, new_state: GuardState, reason: str, now: Optional[float] = None) -> None:
        """Execute state transition and notify listeners."""
        if new_state == self.state:
            return

        old_state = self.state
        self.state = new_state
        self._last_state_change_ts = now if now is not None else time.time()
        self._stats["state_transitions"] += 1

        # Log with appropriate severity
        state_icons = {
            GuardState.HEALTHY: "✅",
            GuardState.CAUTION: "⚠️",
            GuardState.CRITICAL: "🚨",
            GuardState.TERMINAL: "💀",
        }
        icon = state_icons.get(new_state, "❓")

        log_fn = logger.info if new_state <= GuardState.CAUTION else logger.critical
        log_fn(f"{icon} GUARD STATE: {old_state.name} → {new_state.name} | {reason}")

        # Notify all listeners
        for listener in self._state_listeners:
            try:
                listener(old_state, new_state, reason)
            except Exception as e:
                logger.error(f"❌ Guard listener error: {e}")

    # =========================================================
    # OBSERVABILITY
    # =========================================================

    def get_stats(self) -> Dict:
        """Get guard statistics for dashboard/logging."""
        return {
            "state": self.state.name,
            "consecutive_losses": self._consecutive_losses,
            "sizing_violations": self._sizing_violations,
            "session_peak_equity": self._session_peak_equity,
            "current_equity": self._balance_history[-1].equity if self._balance_history else 0.0,
            "balance_samples": len(self._balance_history),
            "trade_samples": len(self._trade_results),
            "error_samples": len(self._error_log),
            **self._stats,
        }

    def reset(self) -> None:
        """Reset guard to HEALTHY state (e.g., after manual intervention)."""
        old = self.state
        self.state = GuardState.HEALTHY
        self._consecutive_losses = 0
        self._sizing_violations = 0
        self._error_log.clear()
        self._last_state_change_ts = time.time()
        logger.info(f"🔄 GUARD RESET: {old.name} → HEALTHY (manual)")

    def update_config(
        self,
        min_notional: Optional[float] = None,
        bet_size: Optional[float] = None,
    ) -> None:
        """
        Update dynamic config values (e.g., from exchange or CLI args).
        Called during startup after Flytest/exchange connection.
        """
        if min_notional is not None:
            self.config.min_notional = min_notional
        if bet_size is not None:
            self.config.bet_size = bet_size

        logger.info(
            f"🛡️ Guard config updated: min_notional=${self.config.min_notional:.2f}, "
            f"bet_size={self.config.bet_size:.2%}"
        )
