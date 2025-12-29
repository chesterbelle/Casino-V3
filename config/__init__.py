"""
====================================================
⚙️ CONFIGURACIÓN MODULAR — CASINO V2
====================================================

Configuración organizada por categorías para mejor mantenibilidad.

Uso:
    from config import system, trading, strategy, sensors, exchange

    mode = system.MODE
    tp = trading.TAKE_PROFIT
    kelly = strategy.KELLY_FRACTION
"""

from . import exchange, sensors, strategy, system, trading

__all__ = [
    "system",
    "trading",
    "strategy",
    "sensors",
    "exchange",
]
