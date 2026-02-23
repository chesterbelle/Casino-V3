"""
====================================================
💰 CONFIGURACIÓN DE TRADING — CASINO V2
====================================================

Parámetros financieros y de gestión de riesgo.
"""

# =====================================================
# 💰 CONFIGURACIÓN FINANCIERA
# =====================================================

# Capital inicial con el que empieza el jugador (Ground Truth balance).
# En live trading, se sincroniza automáticamente con el balance real del exchange.
STARTING_BALANCE = 10_000.0

# Multiplicadores de salida estática (respaldo si el sensor no provee metadata).
# Estos valores calculan la distancia porcentual (0.01 = 1.0%) desde el precio de entrada.
TAKE_PROFIT = 0.01  # Target de salida con ganancias
STOP_LOSS = 0.01  # Límite de pérdida máximo aceptado

# Límite de tiempo máximo para mantener una posición abierta (en número de velas).
# Si la posición no toca TP/SL en este tiempo, se activa la salida por tiempo.
MAX_HOLD_BARS = 180  # 180 velas = 3 horas en temporalidad de 1m

# --- Cierre Progresivo (Fase de Drenaje) ---
# Duración de la fase de salida suave antes del apagado total del bot.
DRAIN_PHASE_MINUTES = 45  # Ventana de tiempo para cerrar posiciones gradualmente

# Tasa máxima de cierre (número de posiciones por minuto).
# Evita errores de "Rate Limit" (-1021) en el exchange durante cierres masivos.
DRAIN_MAX_CLOSE_RATE = 5

# Multiplicador para reducir el TP durante la fase inicial de drenaje (Optimistic).
SOFT_EXIT_TP_MULT = 0.5  # Reduce el target al 50% para facilitar el cierre

# Tiempo máximo de espera para confirmar una modificación de TP en el exchange.
GRACEFUL_TP_TIMEOUT = 30.0  # Tolerancia para latencias en la API de Binance/Hyperliquid


# =====================================================
# ⚖️ GESTIÓN DE RIESGO (SIZING)
# =====================================================

# Algoritmo de cálculo para el tamaño de las posiciones:
# - "FIXED_NOTIONAL": El bot arriesga un % fijo del Balance Total (Bet Size * Equity).
# - "FIXED_RISK": El bot calcula el tamaño para que, si toca el Stop Loss, solo pierdas un % fijo del total.
POSITION_SIZING_MODE = "FIXED_NOTIONAL"  # Modo actual activo

# Porcentaje de riesgo máximo del capital por cada operación individual.
# Solo se utiliza cuando POSITION_SIZING_MODE está en "FIXED_RISK".
RISK_PER_TRADE = 0.01  # 1% de riesgo total por trade


# =====================================================
# 🪙 PERFIL DEL CASINO (GENERAL)
# =====================================================

# Configuración básica de trading
# Nivel máximo de apalancamiento permitido en el exchange.
MAX_LEVERAGE = 50

# Tamaño máximo permitido para una sola posición como % del capital total.
# Filtro de seguridad para evitar sobre-exposición accidental.
MAX_POSITION_SIZE = 0.08  # Máximo 8% del balance total por símbolo

# Tasa de comisión estimada (Fee) para el cálculo de PnL neto.
COMMISSION_RATE = 0.00035  # Basado en Hyperliquid Taker Fee (0.035%)

# Diferencia estimada entre el precio esperado y el ejecutado (Slippage).
SLIPPAGE_DEFAULT = 0.0003  # 0.03% de margen de error en ejecución

# Margen mínimo requerido para mantener una posición abierta antes de liquidación.
MAINTENANCE_MARGIN_RATE = 0.003  # 0.3% del nocional de la posición

# Tipo de margen por defecto para las cuentas de futuros.
DEFAULT_MARGIN_TYPE = "ISOLATED"  # Aislado protege el resto del balance de liquidación


# =====================================================
# 🚪 EXIT STRATEGY (Dynamic Exit Management)
# =====================================================

# --- Trailing Stop ---
# Dynamic SL that follows price when it moves in favor.
# Best for Capturing Trends but can be stopped out by noise in Scalping.
TRAILING_STOP_ENABLED = True  # Shadow Trailing Enabled
TRAILING_STOP_ACTIVATION_PCT = 0.005  # Profit threshold (0.5%) before SL starts trailing
TRAILING_STOP_DISTANCE_PCT = 0.003  # Distance (0.3%) from the peak price to set the trailing SL

# --- Breakeven ---
# Move SL to entry price to secure risk-free trade once a target is reached.
BREAKEVEN_ENABLED = True
BREAKEVEN_ACTIVATION_PCT = 0.003  # Profit threshold (0.3%) to trigger SL move to Entry Price

# --- Signal Reversal ---
# Close position if a strong opposite signal is detected from consensus.
SIGNAL_REVERSAL_ENABLED = False  # Deactivated as per user request (threshold mismatch)
SIGNAL_REVERSAL_THRESHOLD = 0.8  # Required confidence (0-1) to trigger an immediate market close
GRACEFUL_SL_TIMEOUT = 10.0  # Seconds to wait for SL modification before considering it a failure

# =====================================================
# 💧 FILTROS DE LIQUIDEZ (FLYTEST)
# =====================================================

# Volumen mínimo en 24h para permitir trading (en USDT)
# Protege contra monedas "zombie" o con spreads masivos.
FLYTEST_MIN_24H_VOLUME_USDT = 250_000.0  # $250k min volume

# Spread máximo permitido (en % decimal, e.g. 0.005 = 0.5%)
# Si el bid-ask es más ancho, se rechaza.
FLYTEST_MAX_SPREAD_PCT = 0.008  # 0.8% max spread

# Depth Check (Flytest 2.0)
# Required liquidity multiplier relative to bet size (e.g., 3.0 = need 3x bet size in order book)
FLYTEST_MIN_DEPTH_MULT = 3.0

# Depth distance to check from mid-price (e.g., 0.01 = check liquidity within +/- 1%)
FLYTEST_DEPTH_CHECK_PCT = 0.01

# =====================================================
# 🌍 MULTI-ASSET CONFIGURATION
# =====================================================
# Flytest will filter symbols based on MIN_NOTIONAL requirements:
# BTC=$100, ETH=$20, LTC/SOL/BNB=$10. BTC will be rejected with low balance.
MULTI_ASSET_TARGETS = [
    "BTC/USDT",
    "ETH/USDT",
    "XRP/USDT",
    "BCH/USDT",
    "LTC/USDT",
    "EOS/USDT",
    "ETC/USDT",
    "LINK/USDT",
    "XLM/USDT",
    "ADA/USDT",
    "DASH/USDT",
    "ZEC/USDT",
    "XTZ/USDT",
    "BNB/USDT",
    "ATOM/USDT",
    "ONT/USDT",
    "IOTA/USDT",
    "BAT/USDT",
    "VET/USDT",
    "NEO/USDT",
    "QTUM/USDT",
    "IOST/USDT",
    "THETA/USDT",
    "ALGO/USDT",
    "ZIL/USDT",
    "KNC/USDT",
    "ZRX/USDT",
    "COMP/USDT",
    "OMG/USDT",
    "DOGE/USDT",
    "SXP/USDT",
    "KAVA/USDT",
    "BAND/USDT",
    "RLC/USDT",
    "WAVES/USDT",
    "MKR/USDT",
    "SNX/USDT",
    "DOT/USDT",
    "DEFI/USDT",
    "YFI/USDT",
    "BAL/USDT",
    "CRV/USDT",
    "TRB/USDT",
    "RUNE/USDT",
    "SUSHI/USDT",
    "EGLD/USDT",
    "SOL/USDT",
    "ICX/USDT",
    "STORJ/USDT",
]
