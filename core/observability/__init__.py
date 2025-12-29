"""Observability Package."""

from .logging_config import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    unbind_context,
)
from .metrics import (
    record_error,
    record_order_created,
    record_order_failed,
    record_order_filled,
    record_position_closed,
    record_position_opened,
    set_circuit_breaker_state,
    update_balance,
    update_performance_metrics,
    update_unrealized_pnl,
)
from .metrics_server import start_metrics_server, stop_metrics_server

__all__ = [
    # Logging
    "configure_logging",
    "get_logger",
    "bind_context",
    "unbind_context",
    "clear_context",
    # Metrics
    "record_order_created",
    "record_order_filled",
    "record_order_failed",
    "record_position_opened",
    "record_position_closed",
    "record_error",
    "update_balance",
    "update_unrealized_pnl",
    "update_performance_metrics",
    "set_circuit_breaker_state",
    # Server
    "start_metrics_server",
    "stop_metrics_server",
]
