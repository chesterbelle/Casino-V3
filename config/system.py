"""
====================================================
🎯 CONFIGURACIÓN DEL SISTEMA — CASINO V2
====================================================

Parámetros de ejecución, logging y control del sistema.
"""

import os
import sys
from typing import Literal

# =====================================================
# 🎯 MODO DEL CASINO
# =====================================================

_MODE_ENV_VAR = "CASINO_MODE"
_ALLOWED_MODES = {"backtest", "demo", "live"}


def _get_mode(default: Literal["backtest", "demo", "live"]) -> Literal["backtest", "demo", "live"]:
    value = os.getenv(_MODE_ENV_VAR)
    if value:
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_MODES:
            raise ValueError(f"Invalid MODE: {value}. Must be one of {_ALLOWED_MODES}")
        return normalized
    return default


# Modo de operación:
#  - "backtest" → usa dataset CSV y simula operaciones históricas
#  - "demo"     → conecta a Bybit Demo Trading (precios reales, trades simulados)
#  - "live"     → trading real con dinero real
MODE: Literal["backtest", "demo", "live"] = _get_mode("demo")


# =====================================================
# 🚨 VALIDACIONES DE SEGURIDAD PARA LIVE TRADING
# =====================================================

_LIVE_CONFIG_ENV = "CASINO_LIVE_TRADING_ENABLED_CONFIG"
LIVE_TRADING_ENABLED_DEFAULT = False
LIVE_TRADING_ENABLED = bool(
    LIVE_TRADING_ENABLED_DEFAULT or os.getenv(_LIVE_CONFIG_ENV, "false").strip().lower() == "true"
)
LIVE_CONFIRMATION_KEYWORD = "YES"
LIVE_ENV_FLAG = "CASINO_LIVE_TRADING_ENABLED"


# =====================================================
# ⏱️ CONTROL DE SESIONES
# =====================================================

# Delay entre iteraciones del loop live (segundos)
LIVE_SLEEP_SECONDS = 1.0

# Número máximo de velas a procesar antes de detener la sesión.
# Usa None (o valores <= 0) para dejarlo en ejecución indefinida.
LIVE_MAX_CANDLES = 30  # Prueba manual limitada a 30 velas


# =====================================================
# 📁 RUTAS Y ARCHIVOS
# =====================================================

# Ruta del dataset CSV (para modo backtest)
DATASET_PATH = "tables/data/raw/LTCUSDT_1m__1d.csv"

# Archivos de resultados y logs
SAVE_RESULTS = True
RESULTS_FILE = "casino_results.csv"
DECISIONS_LOG_PATH = "gemini/data/gemini_decisions.csv"
TRADE_RESULTS_LOG_PATH = "gemini/data/gemini_trade_results.csv"


# =====================================================
# 🧾 LOGGING
# =====================================================

# Nivel de detalle del log (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL = "INFO"


# =====================================================
# 🧱 REPRODUCIBILIDAD
# =====================================================

# Semilla aleatoria para reproducibilidad
SEED = 42


# =====================================================
# 🚨 VALIDACIÓN DE LIVE TRADING AL IMPORTAR
# =====================================================

if MODE == "live":  # pragma: no cover - interacción manual requerida
    if os.getenv(LIVE_ENV_FLAG, "").lower() != "true":
        msg = (
            "\n" + "=" * 70 + "\n"
            "🚨 LIVE TRADING DESHABILITADO 🚨\n" + "=" * 70 + "\n\n"
            "Live trading requiere confirmación explícita.\n"
            "Para habilitarlo ejecuta:\n"
            "    export CASINO_LIVE_TRADING_ENABLED=true\n"
            "(y asegúrate de ejecutar en un entorno seguro).\n"
        )
        print(msg)
        sys.exit(1)

    if not LIVE_TRADING_ENABLED:
        msg = (
            "\n" + "=" * 70 + "\n"
            "❌ LIVE_TRADING_ENABLED=False en config/system.py\n" + "=" * 70 + "\n\n"
            "Para activar live trading debes establecer:\n"
            "  - config/system.py → LIVE_TRADING_ENABLED_DEFAULT = True\n"
            "    o bien\n"
            "  - export CASINO_LIVE_TRADING_ENABLED_CONFIG=true\n"
            "Solo hazlo si estás listo para operar con dinero real.\n"
        )
        print(msg)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("⚠️  CONFIRMACIÓN DE LIVE TRADING (DINERO REAL) ⚠️")
    print("=" * 70)
    print(f"Modo: {MODE}")
    print()
    print("⚠️  ESTO USARÁ DINERO REAL")
    print(f"Escribe '{LIVE_CONFIRMATION_KEYWORD}' para continuar.")

    try:
        confirmation = input("Confirmación: ").strip()
    except EOFError:
        confirmation = ""

    if confirmation != LIVE_CONFIRMATION_KEYWORD:
        print("\n❌ Live trading cancelado por el usuario\n")
        sys.exit(0)

    print("\n✅ Live trading confirmado. Procediendo bajo tu responsabilidad.\n")
