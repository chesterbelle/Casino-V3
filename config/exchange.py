"""
====================================================
🏦 CONFIGURACIÓN DE EXCHANGES — CASINO V2
====================================================

Parámetros de conexión a exchanges y símbolos.
"""

import os
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

# =====================================================
# 🏦 EXCHANGE ACTIVO
# =====================================================

_EXCHANGE_ENV_VAR = "CASINO_EXCHANGE"
_ALLOWED_EXCHANGES = {"BINANCE", "HYPERLIQUID"}


def _get_exchange(
    default: Literal["BINANCE", "HYPERLIQUID"],
) -> Literal["BINANCE", "HYPERLIQUID"]:
    value = os.getenv(_EXCHANGE_ENV_VAR)
    if value:
        normalized = value.strip().upper()
        if normalized not in _ALLOWED_EXCHANGES:
            raise ValueError(f"Exchange inválido '{value}'. Usa uno de {_ALLOWED_EXCHANGES}.")
        return normalized  # type: ignore[return-value]
    return default


# Exchange activo (se usa en modos testing/live)
# Opciones actuales:
#  - "BINANCE"    → Binance Futures
#  - "HYPERLIQUID"→ Hyperliquid
EXCHANGE: Literal["BINANCE", "HYPERLIQUID"] = _get_exchange("BINANCE")

# Perfil del exchange (usa el JSON de tables/data/exchange_profiles)
EXCHANGE_PROFILE = "kraken_futures_demo"

# Símbolo y timeframe por defecto
SYMBOL = "BTC/USD"
TIMEFRAME = "15m"

# Moneda base para cálculos de balance y PnL
BASE_CURRENCY = "USDT"


# =====================================================
# BINANCE FUTURES — PARÁMETROS TESTNET/LIVE
# =====================================================

BINANCE_BASE_URL = "https://testnet.binancefuture.com"
BINANCE_DEFAULT_SYMBOL = "BTC/USDT"
BINANCE_DEFAULT_INTERVAL = "15m"
BINANCE_POLL_INTERVAL = 2.0
BINANCE_API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_TESTNET_SECRET")


# =====================================================
# HYPERLIQUID — PARÁMETROS LIVE
# =====================================================

HYPERLIQUID_BASE_URL = "https://api.hyperliquid.xyz"
HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"
HYPERLIQUID_DEFAULT_SYMBOL = "LTC"
HYPERLIQUID_DEFAULT_INTERVAL = "1m"
HYPERLIQUID_POLL_INTERVAL = 1.0
HYPERLIQUID_API_KEY = None
HYPERLIQUID_API_SECRET = None
HYPERLIQUID_VAULT_ADDRESS = None  # Para vault trading


# =====================================================
# ASTERDEX — PARÁMETROS PAPER/LIVE
# =====================================================

ASTER_BASE_URL = "https://fapi.asterdex.com"
ASTER_WS_URL = "wss://fstream.asterdex.com"
ASTER_DEFAULT_SYMBOL = "LTC"
ASTER_DEFAULT_INTERVAL = "1m"
ASTER_RECV_WINDOW = 5000
ASTER_POLL_INTERVAL = 2.0
ASTER_API_KEY = None
ASTER_API_SECRET = None
