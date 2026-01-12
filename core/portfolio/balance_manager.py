"""
💰 BalanceManager
-----------------
Administra el capital del jugador.
Actualiza equity, PnL y mantiene trazabilidad de operaciones.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("BalanceManager")


class BalanceManager:
    def __init__(self, starting_balance: float):
        self.balance = starting_balance
        self.equity = starting_balance
        self.history = []

    def apply_trade_result(self, pnl: float, fee: float):
        """Aplica el resultado de una operación."""
        self.balance += pnl - fee
        self.equity = self.balance
        self.history.append({"pnl": pnl, "fee": fee, "equity": self.equity})

    def apply_pnl(self, pnl: float, fee: float):
        """Aplica PnL y fees (alias para compatibilidad)."""
        self.apply_trade_result(pnl, fee)

    def can_open_position(self, risk_amount: float) -> bool:
        """Verifica si el jugador puede arriesgar ese monto."""
        return risk_amount <= self.balance

    def get_balance(self) -> float:
        """
        Obtiene el balance actual.

        Returns:
            Balance actual disponible
        """
        return self.balance

    def get_equity(self) -> float:
        """
        Obtiene el equity actual.

        Returns:
            Equity actual (balance + PnL no realizado)
        """
        return self.equity

    def set_balance(self, new_balance: float):
        """
        Actualiza el balance con un valor del exchange.

        CRÍTICO: Este método se usa para sincronizar el balance local
        con el balance real del exchange después de cada trade.
        """
        self.balance = new_balance
        self.equity = new_balance

    def update_balance(self, delta: float):
        """
        Actualiza el balance con un delta (positivo o negativo).

        Args:
            delta: Cambio en el balance (puede ser negativo)
        """
        self.balance += delta
        self.equity = self.balance

    def reserve_margin(self, amount: float):
        """
        Bloquea capital para una posición.
        (En Casino-V3 el margin se resta del可用 balance local para sizing).
        """
        self.balance -= amount
        self.equity = self.balance

    def handle_account_update(self, event: Dict[str, Any]):
        """
        Calcula el balance y equity en tiempo real desde un evento ACCOUNT_UPDATE.
        (Phase 46: Real-Time Shadow Balance).
        """
        # Binance ACCOUNT_UPDATE (WS) format: { 'B': [{'a': 'USDT', 'wb': '100.5', 'cw': '100.5'}] }
        balances = event.get("B", [])
        for b in balances:
            asset = b.get("a")
            if asset == "USDT":
                wallet_balance = float(b.get("wb", self.balance))
                # Update balance and equity
                self.balance = wallet_balance
                self.equity = wallet_balance  # In a more complex setup, we'd add unrealized PnL
                # self.logger.info(f"💰 Real-Time Balance Update: {self.balance:.2f} USDT")
                break

    def get_state(self):
        """Snapshot actual del capital."""
        return {"balance": round(self.balance, 4), "equity": round(self.equity, 4), "trades": len(self.history)}
