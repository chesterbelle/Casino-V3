"""
Resilience Package - Componentes para operación robusta 24/7.

Este paquete contiene:
- ConnectionManager: WebSocket + REST fallback con reconexión automática
- StateRecovery: Recuperación de estado después de crashes
- Circuit breaker pattern
- Health checks
- Métricas de conexión

Author: Casino V3 Team
Version: 2.0.0
"""

from .connection_manager import (
    CircuitState,
    ConnectionManager,
    ConnectionMetrics,
    ConnectionState,
)
from .state_recovery import SessionState, StateRecovery

__all__ = [
    "ConnectionManager",
    "ConnectionState",
    "CircuitState",
    "ConnectionMetrics",
    "StateRecovery",
    "SessionState",
]
