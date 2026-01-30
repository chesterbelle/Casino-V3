"""
Portfolio Manager - Casino V3

Centraliza la gestión de balance y posiciones.
Gestiona balance y tracking simple de posiciones.
"""

import logging
from typing import Dict, List, Optional

from .balance_manager import BalanceManager

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Gestor centralizado de portfolio.

    Responsabilidades:
    - Gestión de balance (disponible vs. bloqueado)
    - Tracking de posiciones abiertas
    - Cálculo de equity
    - Validación de fondos

    Usa:
    - BalanceManager: Gestión de capital
    - Dict interno: Tracking simple de posiciones
    """

    def __init__(self, initial_balance: float):
        """
        Inicializa el portfolio manager.

        Args:
            initial_balance: Balance inicial en USDT
        """
        self.balance_manager = BalanceManager(initial_balance)
        self.positions: Dict[str, Dict] = {}  # trade_id -> position info
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"💼 Portfolio initialized with balance: ${initial_balance:,.2f}")

    # ========================================
    # API Pública: Consultas
    # ========================================

    def get_balance(self) -> float:
        """
        Retorna el balance disponible (cash).

        Returns:
            Balance en USDT
        """
        return self.balance_manager.balance

    def get_equity(self) -> float:
        """
        Retorna el equity total (balance + valor de posiciones).

        Returns:
            Equity total en USDT
        """
        return self.balance_manager.equity

    def get_open_positions(self) -> List[Dict]:
        """
        Retorna lista de posiciones abiertas.

        Returns:
            Lista de diccionarios con info de posiciones
        """
        return list(self.positions.values())

    def get_position(self, trade_id: str) -> Optional[Dict]:
        """
        Obtiene una posición específica por trade_id.

        Args:
            trade_id: ID del trade

        Returns:
            Diccionario con info de la posición o None si no existe
        """
        return self.positions.get(trade_id)

    def get_portfolio_state(self) -> Dict:
        """
        Retorna el estado completo del portfolio.

        Returns:
            Diccionario con balance, equity, y posiciones
        """
        open_positions = self.get_open_positions()
        return {
            "balance": self.get_balance(),
            "equity": self.get_equity(),
            "open_positions_count": len(open_positions),
            "open_positions": open_positions,
        }

    # ========================================
    # API Pública: Validaciones
    # ========================================

    def can_open_position(self, size: float) -> bool:
        """
        Valida si hay fondos suficientes para abrir una posición.

        Args:
            size: Tamaño de la posición en USDT

        Returns:
            True si hay fondos suficientes, False en caso contrario
        """
        return self.balance_manager.balance >= size

    def get_available_size(self) -> float:
        """
        Retorna el tamaño máximo disponible para una nueva posición.

        Returns:
            Balance disponible en USDT
        """
        return self.balance_manager.balance

    # ========================================
    # API Pública: Operaciones
    # ========================================

    def open_position(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        take_profit: float,
        stop_loss: float,
        timestamp: Optional[str] = None,
    ) -> Dict:
        """
        Registra la apertura de una posición.

        Args:
            trade_id: ID único del trade
            symbol: Símbolo del activo
            side: "LONG" o "SHORT"
            size: Tamaño de la posición en USDT
            entry_price: Precio de entrada
            take_profit: Precio de take profit
            stop_loss: Precio de stop loss
            timestamp: Timestamp de apertura (opcional)

        Returns:
            Diccionario con el resultado de la operación

        Raises:
            ValueError: Si no hay fondos suficientes
        """
        # Validar fondos
        if not self.can_open_position(size):
            raise ValueError(f"Insufficient funds: need ${size:,.2f}, have ${self.get_balance():,.2f}")

        # Reservar fondos (reducir balance disponible)
        self.balance_manager.add_balance_delta(-size)

        # Registrar posición
        self.positions[trade_id] = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "timestamp": timestamp,
            "status": "open",
        }

        self.logger.info(
            f"📈 Position opened: {trade_id} | {symbol} {side} | " f"size=${size:,.2f} @ {entry_price:.2f}"
        )

        return {
            "status": "opened",
            "trade_id": trade_id,
            "balance": self.get_balance(),
            "equity": self.get_equity(),
        }

    def close_position(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        fee: float = 0.0,
        timestamp: Optional[str] = None,
    ) -> Dict:
        """
        Cierra una posición y actualiza el balance.

        Args:
            trade_id: ID del trade a cerrar
            exit_price: Precio de salida
            exit_reason: Razón de cierre ("TP", "SL", "manual", etc.)
            fee: Comisiones totales
            timestamp: Timestamp de cierre (opcional)

        Returns:
            Diccionario con el resultado (pnl, balance, etc.)

        Raises:
            ValueError: Si la posición no existe
        """
        # Obtener posición
        position = self.get_position(trade_id)
        if not position:
            raise ValueError(f"Position not found: {trade_id}")

        # Calcular PnL
        pnl = self._calculate_pnl(position, exit_price, fee)

        # Remover posición del tracking
        del self.positions[trade_id]

        # Liberar fondos (devolver el tamaño de la posición) y aplicar PnL
        self.balance_manager.add_balance_delta(position["size"])  # Devolver fondos reservados
        self.balance_manager.apply_pnl(pnl, fee)  # Aplicar resultado neto

        result = "WIN" if pnl > 0 else "LOSS"

        self.logger.info(
            f"📉 Position closed: {trade_id} | {exit_reason} | "
            f"PnL=${pnl:,.2f} ({result}) | Balance=${self.get_balance():,.2f}"
        )

        return {
            "status": "closed",
            "trade_id": trade_id,
            "result": result,
            "pnl": pnl,
            "fee": fee,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "balance": self.get_balance(),
            "equity": self.get_equity(),
        }

    # ========================================
    # Métodos Privados
    # ========================================

    def _calculate_pnl(self, position: Dict, exit_price: float, fee: float) -> float:
        """
        Calcula el PnL de una posición.

        Args:
            position: Diccionario con info de la posición
            exit_price: Precio de salida
            fee: Comisiones totales

        Returns:
            PnL neto (después de fees)
        """
        entry_price = position["entry_price"]
        size = position["size"]
        side = position["side"]

        # Calcular PnL bruto
        if side == "LONG":
            pnl_pct = (exit_price - entry_price) / entry_price
        else:  # SHORT
            pnl_pct = (entry_price - exit_price) / entry_price

        pnl_gross = size * pnl_pct

        # Restar fees
        pnl_net = pnl_gross - fee

        return pnl_net

    # ========================================
    # API Pública: Estado y Reset
    # ========================================

    def reset(self, new_balance: float):
        """
        Resetea el portfolio a un nuevo balance.

        Args:
            new_balance: Nuevo balance inicial
        """
        self.balance_manager = BalanceManager(new_balance)
        self.positions = {}  # Reset positions
        self.logger.info(f"🔄 Portfolio reset to ${new_balance:,.2f}")

    def get_statistics(self) -> Dict:
        """
        Retorna estadísticas del portfolio.

        Returns:
            Diccionario con estadísticas
        """
        return {
            "balance": self.get_balance(),
            "equity": self.get_equity(),
            "open_positions": len(self.get_open_positions()),
        }
