"""
HFT Exit Manager - Phase 1000 Dumb Execution Layer

Ultra-minimal exit management for high-frequency scalping.
Philosophy: "The best exit manager is the one that does nothing."

Trusts OCO brackets completely. Only intervenes on true catastrophes.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

import config.trading as config
from core.events import TickEvent
from utils.symbol_norm import normalize_symbol

if TYPE_CHECKING:
    from croupier.croupier import Croupier


logger = logging.getLogger("HFTExitManager")


class HFTExitManager:
    """
    Phase 1000: Dumb Execution Layer

    Replaces the complex ExitManager for HFT scalping scenarios.
    Eliminates all shadow interventions, breakeven logic, and
    tactical airbags that were eroding the strategy edge.

    Only responsibility: Prevent liquidation on catastrophic moves.
    Everything else is handled by the OCO brackets placed at entry.
    """

    def __init__(self, croupier: "Croupier"):
        self.croupier = croupier
        self.logger = logger

        # Minimal configuration
        self.catastrophic_drawdown_pct = getattr(config, "CATASTROPHIC_STOP_PCT", 0.50)

        self.logger.info(
            "🎯 HFTExitManager initialized | "
            f"Catastrophic stop: {self.catastrophic_drawdown_pct:.1%} | "
            "Mode: DUMB (trust OCO)"
        )

    async def on_tick(self, event: TickEvent):
        """
        ÚNICA responsabilidad: Detectar catastrófico y cerrar.

        Catastrófico = >50% drawdown (imposible en condiciones normales
        de scalping, solo ocurre en black swan / liquidation cascade).
        """
        if not getattr(config, "HFT_EXIT_MODE", False):
            return

        symbol_norm = normalize_symbol(event.symbol)
        positions = self.croupier.position_tracker.get_positions_by_symbol(symbol_norm)

        for position in positions:
            # Skip already closing
            if position.status == "CLOSING":
                continue

            # Calculate drawdown
            if position.entry_price <= 0:
                continue

            if position.side == "LONG":
                drawdown = (position.entry_price - event.price) / position.entry_price
            else:
                drawdown = (event.price - position.entry_price) / position.entry_price

            # Solo catastrófico
            if drawdown > self.catastrophic_drawdown_pct:
                self.logger.critical(
                    f"🚨 CATASTROPHIC STOP triggered for {position.trade_id} | "
                    f"Drawdown: {drawdown:.1%} | Price: {event.price:.4f}"
                )
                asyncio.create_task(self.croupier.close_position(position.trade_id, exit_reason="CATASTROPHIC_STOP"))

    async def on_signal(self, event):
        """NO-OP: No signal reversal in HFT mode."""
        pass

    async def on_candle(self, event):
        """NO-OP: No time-based exits in HFT mode."""
        pass

    async def on_microstructure(self, event):
        """NO-OP: No tactical airbag in HFT mode."""
        pass

    async def trigger_soft_exits(self):
        """NO-OP: No soft exits in HFT mode."""
        pass

    async def trigger_defensive_exits(self):
        """NO-OP: No defensive exits in HFT mode."""
        pass

    async def trigger_aggressive_exits(self, fraction: float = 0.2):
        """NO-OP: No aggressive exits in HFT mode."""
        pass

    async def apply_dynamic_exit(self, position, phase: str):
        """NO-OP: No dynamic exits in HFT mode."""
        pass
