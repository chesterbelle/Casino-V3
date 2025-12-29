"""
💰 BalanceManager
-----------------
Administra el capital del jugador.
Actualiza equity, PnL y mantiene trazabilidad de operaciones.
"""


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

    def get_state(self):
        """Snapshot actual del capital."""
        return {"balance": round(self.balance, 4), "equity": round(self.equity, 4), "trades": len(self.history)}
