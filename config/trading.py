"""
====================================================
💰 CONFIGURACIÓN DE TRADING — CASINO V2
====================================================

Parámetros financieros y de gestión de riesgo.
"""

# =====================================================
# 💰 CONFIGURACIÓN FINANCIERA
# =====================================================

# Capital inicial con el que empieza el jugador
# En live trading, se sincroniza con el balance real del exchange
STARTING_BALANCE = 10_000.0

# Tamaños relativos de TP y SL (expresados en proporción decimal)
# Proven values from 90-day backtest (50.8% WR, +0.25% PnL)
TAKE_PROFIT = 0.01  # 1.0% target
STOP_LOSS = 0.01  # 1.0% stop

# Time-Based Exit (Optimization Alignment)
MAX_HOLD_BARS = 180  # Increase to 3h for more natural exits

# --- Graceful Exit (Soft Timeout) ---
DRAIN_PHASE_MINUTES = 30  # Stop new entries 30 min before timeout
SOFT_EXIT_TP_MULT = 0.5  # Narrow TP by 50% for soft exit
GRACEFUL_TP_TIMEOUT = 5.0  # Seconds to wait for TP modification before skipping


# =====================================================
# ⚖️ GESTIÓN DE RIESGO (SIZING)
# =====================================================

# Modo de cálculo de tamaño de posición:
# - "FIXED_NOTIONAL": Usa el Bet Size como % del Balance Total (Ej. 1% balance = 34 USDT)
# - "FIXED_RISK":     Usa el Bet Size como % de RIESGO en Stop Loss (Ej. 1% riesgo + 1% SL = 3400 USDT)
POSITION_SIZING_MODE = "FIXED_NOTIONAL"  # ACTIVATED

# Riesgo por operación (Solo usado si POSITION_SIZING_MODE = "FIXED_RISK")
# Si bet-size es 1.0 (1%), se arriesga el 1% del balance en caso de stop loss.
RISK_PER_TRADE = 0.01


# =====================================================
# 🪙 PERFIL DEL CASINO (GENERAL)
# =====================================================

# Configuración básica de trading
MAX_LEVERAGE = 50  # máximo apalancamiento permitido
MAX_POSITION_SIZE = 0.08  # tamaño máximo conservador (8% del equity)
COMMISSION_RATE = 0.00035  # Hyperliquid taker fee (0.035%)
SLIPPAGE_DEFAULT = 0.0003  # spread estimado
MAINTENANCE_MARGIN_RATE = 0.003  # margen de mantenimiento (0.3%)
DEFAULT_MARGIN_TYPE = "ISOLATED"  # Opciones: ISOLATED, CROSSED


# =====================================================
# 🚪 EXIT STRATEGY (Dynamic Exit Management)
# =====================================================

# --- Trailing Stop ---
# Dynamic SL that follows price when it moves in favor
TRAILING_STOP_ENABLED = True
TRAILING_STOP_ACTIVATION_PCT = 0.005  # Activate after 0.5% profit
TRAILING_STOP_DISTANCE_PCT = 0.003  # Maintain 0.3% distance from peak

# --- Breakeven ---
# Move SL to entry price to secure risk-free trade
BREAKEVEN_ENABLED = True
BREAKEVEN_ACTIVATION_PCT = 0.003  # Move to BE after 0.3% profit

# --- Signal Reversal ---
# Close position if a strong opposite signal is detected
SIGNAL_REVERSAL_ENABLED = True
SIGNAL_REVERSAL_THRESHOLD = 0.8  # Confidence threshold for reversal signal

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
    "BCH/USDT",
    "XRP/USDT",
    "EOS/USDT",
    "LTC/USDT",
    "TRX/USDT",
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
