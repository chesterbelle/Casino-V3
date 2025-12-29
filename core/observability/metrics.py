"""
Prometheus Metrics for Casino V3.

Provides comprehensive metrics for monitoring bot performance.

Author: Casino V3 Team
Version: 2.0.0
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ============================================================================
# COUNTERS (monotonically increasing)
# ============================================================================

# Orders
orders_created_total = Counter(
    "orders_created_total",
    "Total number of orders created",
    ["exchange", "symbol", "side", "type"],
)

orders_filled_total = Counter(
    "orders_filled_total",
    "Total number of orders filled",
    ["exchange", "symbol", "side"],
)

orders_failed_total = Counter(
    "orders_failed_total",
    "Total number of failed orders",
    ["exchange", "reason"],
)

orders_cancelled_total = Counter(
    "orders_cancelled_total",
    "Total number of cancelled orders",
    ["exchange", "symbol", "reason"],
)

# Positions
positions_opened_total = Counter(
    "positions_opened_total",
    "Total number of positions opened",
    ["symbol", "side"],
)

positions_closed_total = Counter(
    "positions_closed_total",
    "Total number of positions closed",
    ["symbol", "reason"],
)

# Trades
trades_won_total = Counter(
    "trades_won_total",
    "Total number of winning trades",
    ["symbol"],
)

trades_lost_total = Counter(
    "trades_lost_total",
    "Total number of losing trades",
    ["symbol"],
)

# Errors
errors_total = Counter(
    "errors_total",
    "Total number of errors",
    ["component", "category", "retriable"],
)

# WebSocket
websocket_messages_total = Counter(
    "websocket_messages_total",
    "Total WebSocket messages received",
    ["exchange", "type"],
)

websocket_reconnections_total = Counter(
    "websocket_reconnections_total",
    "Total WebSocket reconnections",
    ["exchange", "reason"],
)

# ============================================================================
# GAUGES (can go up and down)
# ============================================================================

# Balance
account_balance_usdt = Gauge(
    "account_balance_usdt",
    "Current account balance in USDT",
    ["exchange"],
)

available_balance_usdt = Gauge(
    "available_balance_usdt",
    "Available balance in USDT",
    ["exchange"],
)

allocated_balance_usdt = Gauge(
    "allocated_balance_usdt",
    "Allocated balance in USDT",
    ["exchange"],
)

# Positions
open_positions = Gauge(
    "open_positions",
    "Number of currently open positions",
    ["symbol"],
)

unrealized_pnl_usdt = Gauge(
    "unrealized_pnl_usdt",
    "Unrealized PnL in USDT",
    ["symbol"],
)

realized_pnl_usdt = Gauge(
    "realized_pnl_usdt",
    "Cumulative realized PnL in USDT",
)

# Performance
win_rate = Gauge(
    "win_rate",
    "Current win rate (percentage)",
)

profit_factor = Gauge(
    "profit_factor",
    "Profit factor (gross profit / gross loss)",
)

# System
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["name"],
)

state_save_age_seconds = Gauge(
    "state_save_age_seconds",
    "Seconds since last state save",
)

event_loop_lag_seconds = Gauge(
    "event_loop_lag_seconds",
    "Event loop lag in seconds",
)

# ============================================================================
# HISTOGRAMS (distribution of values)
# ============================================================================

# Latency
order_latency_seconds = Histogram(
    "order_latency_seconds",
    "Order execution latency in seconds",
    ["exchange", "type"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

websocket_latency_seconds = Histogram(
    "websocket_latency_seconds",
    "WebSocket message latency in seconds",
    ["exchange"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

reconciliation_duration_seconds = Histogram(
    "reconciliation_duration_seconds",
    "Position reconciliation duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Trade metrics
trade_pnl_usdt = Histogram(
    "trade_pnl_usdt",
    "Trade PnL in USDT",
    ["symbol"],
    buckets=[-1000, -500, -100, -50, -10, 0, 10, 50, 100, 500, 1000],
)

trade_duration_seconds = Histogram(
    "trade_duration_seconds",
    "Trade duration in seconds",
    ["symbol"],
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400, 28800, 86400],
)

# ============================================================================
# INFO (static labels)
# ============================================================================

bot_info = Info(
    "bot_info",
    "Bot version and configuration",
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def record_order_created(exchange: str, symbol: str, side: str, order_type: str):
    """Record order creation."""
    orders_created_total.labels(
        exchange=exchange,
        symbol=symbol,
        side=side,
        type=order_type,
    ).inc()


def record_order_filled(exchange: str, symbol: str, side: str):
    """Record order fill."""
    orders_filled_total.labels(
        exchange=exchange,
        symbol=symbol,
        side=side,
    ).inc()


def record_order_failed(exchange: str, reason: str):
    """Record order failure."""
    orders_failed_total.labels(
        exchange=exchange,
        reason=reason,
    ).inc()


def record_position_opened(symbol: str, side: str):
    """Record position opening."""
    positions_opened_total.labels(symbol=symbol, side=side).inc()
    open_positions.labels(symbol=symbol).inc()


def record_position_closed(symbol: str, reason: str, pnl: float, won: bool):
    """Record position closing."""
    positions_closed_total.labels(symbol=symbol, reason=reason).inc()
    open_positions.labels(symbol=symbol).dec()

    # Record PnL
    trade_pnl_usdt.labels(symbol=symbol).observe(pnl)

    # Record win/loss
    if won:
        trades_won_total.labels(symbol=symbol).inc()
    else:
        trades_lost_total.labels(symbol=symbol).inc()


def record_error(component: str, category: str, retriable: bool):
    """Record error."""
    errors_total.labels(
        component=component,
        category=category,
        retriable=str(retriable),
    ).inc()


def update_balance(exchange: str, total: float, available: float, allocated: float):
    """Update balance metrics."""
    account_balance_usdt.labels(exchange=exchange).set(total)
    available_balance_usdt.labels(exchange=exchange).set(available)
    allocated_balance_usdt.labels(exchange=exchange).set(allocated)


def update_unrealized_pnl(symbol: str, pnl: float):
    """Update unrealized PnL."""
    unrealized_pnl_usdt.labels(symbol=symbol).set(pnl)


def update_performance_metrics(win_rate_pct: float, profit_factor_val: float):
    """Update performance metrics."""
    win_rate.set(win_rate_pct)
    profit_factor.set(profit_factor_val)


def set_circuit_breaker_state(name: str, state: int):
    """
    Set circuit breaker state.

    Args:
        name: Circuit breaker name
        state: 0=closed, 1=open, 2=half_open
    """
    circuit_breaker_state.labels(name=name).set(state)


def update_loop_lag(lag: float):
    """Update event loop lag metric."""
    event_loop_lag_seconds.set(lag)
