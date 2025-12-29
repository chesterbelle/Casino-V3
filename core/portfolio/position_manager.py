"""
====================================================
♟️ Position Manager — Gestor de Estado de Posición
====================================================

Rol:
----
• Mantiene el estado de UNA única posición abierta para una mesa.
• Almacena detalles clave como el lado, tamaño, precio de entrada y niveles de salida.
• Ofrece una interfaz simple para verificar si hay una posición activa y
  comprobar si el precio actual activa un TP/SL.

Modularidad:
------------
Este componente es agnóstico a la estrategia y al exchange. Su única
responsabilidad es el estado, permitiendo que el bucle de sesión
orqueste las acciones (abrir/cerrar) y que la "mesa" (Table) se
encubargue de la comunicación con la API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Position:
    """Representa una única posición de trading abierta."""

    symbol: str
    side: str  # "LONG" o "SHORT"
    size_contracts: float
    entry_price: float
    take_profit_price: float
    stop_loss_price: float
    entry_timestamp: str
    trade_id: str
    misc: Dict[str, Any] = field(default_factory=dict)


class PositionManager:
    """
    Gestiona el ciclo de vida de una posición abierta.
    Diseñado para manejar una posición a la vez.
    """

    def __init__(self) -> None:
        self._open_position: Optional[Position] = None

    def is_position_open(self) -> bool:
        """Devuelve True si hay una posición abierta."""
        return self._open_position is not None

    def get_open_position(self) -> Optional[Position]:
        """Devuelve la posición activa o None."""
        return self._open_position

    def open_position(
        self,
        *,
        symbol: str,
        side: str,
        size_contracts: float,
        entry_price: float,
        take_profit_price: float,
        stop_loss_price: float,
        entry_timestamp: str,
        trade_id: str,
        misc: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Registra una nueva posición abierta.
        Lanza un error si ya existe una.
        """
        if self.is_position_open():
            raise RuntimeError("Ya hay una posición abierta. No se puede abrir otra.")

        self._open_position = Position(
            symbol=symbol,
            side=side.upper(),
            size_contracts=size_contracts,
            entry_price=entry_price,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            entry_timestamp=entry_timestamp,
            trade_id=trade_id,
            misc=misc or {},
        )

    def close_position(self) -> Optional[Position]:
        """
        Cierra la posición activa y la devuelve.
        Si no hay posición, devuelve None.
        """
        closed_position = self._open_position
        self._open_position = None
        return closed_position

    def check_exit(self, high_price: float, low_price: float) -> Optional[str]:
        """
        Comprueba si la vela actual (high/low) activa un TP o SL.
        Devuelve "TP", "SL" o None.
        Prioriza SL si ambos se tocan en la misma vela.
        """
        if not self.is_position_open() or self._open_position is None:
            return None

        pos = self._open_position
        if pos.side == "LONG":
            # Para un LONG, el SL se activa si el precio BAJA a `stop_loss_price`
            if low_price <= pos.stop_loss_price:
                return "SL"
            # El TP se activa si el precio SUBE a `take_profit_price`
            if high_price >= pos.take_profit_price:
                return "TP"
        elif pos.side == "SHORT":
            # Para un SHORT, el SL se activa si el precio SUBE a `stop_loss_price`
            if high_price >= pos.stop_loss_price:
                return "SL"
            # El TP se activa si el precio BAJA a `take_profit_price`
            if low_price <= pos.take_profit_price:
                return "TP"

        return None
