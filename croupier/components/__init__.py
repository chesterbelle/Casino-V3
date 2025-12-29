"""
Croupier Components Package.

Contains specialized components that replace the monolithic Croupier:
- OrderExecutor: Handles individual order execution
- OCOManager: Manages OCO bracket orders (TP/SL)
- ReconciliationService: Syncs state with exchange
- PositionValidator: Validates position integrity
"""

from .order_executor import OrderExecutor

__all__ = ["OrderExecutor"]
