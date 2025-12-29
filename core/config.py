"""
====================================================
⚙️ CONFIGURACIÓN GENERAL — CASINO V2 (LEGACY)
====================================================

⚠️ DEPRECADO: Este archivo se mantiene por compatibilidad.
   Usa la nueva estructura modular en config/ en su lugar:

   from config import system, trading, strategy, sensors, exchange

Este archivo reexporta desde la nueva estructura modular.
====================================================
"""

# Reexportar todo desde módulos nuevos
from config.exchange import *  # noqa: F401, F403
from config.sensors import *  # noqa: F401, F403
from config.strategy import *  # noqa: F401, F403
from config.system import *  # noqa: F401, F403
from config.trading import *  # noqa: F401, F403
