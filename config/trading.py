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

# TP/SL fallback percentages (DECIMAL: 0.003 = 0.3%).
# Used ONLY when sensors don't provide structural price levels.
# These are converted to absolute prices in execution.py.
DEFAULT_TP_PCT = 0.003  # 0.3% from entry
DEFAULT_SL_PCT = 0.002  # 0.2% from entry

# Backward-compatible aliases (used by position_tracker, multi_asset_manager, etc.)
TAKE_PROFIT = DEFAULT_TP_PCT
STOP_LOSS = DEFAULT_SL_PCT

# Límite de tiempo máximo para mantener una posición abierta.
# Phase 974: Sniper Patience Lock - Increased to 60 to permit structural TP development.
MAX_HOLD_BARS = 60  # 60 candles @ 1m = 1 hour window

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
# En Footprint Scalping (operaciones muy frecuentes), el riesgo por trade se reduce drásticamente.
RISK_PER_TRADE = 0.002  # 0.2% de riesgo total por trade


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
# Vital en scalping: si el slippage pasa de 0.015%, se destruye la ventaja matemática.
SLIPPAGE_DEFAULT = 0.00015  # 0.015% de margen de error en ejecución

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
TRAILING_STOP_ENABLED = False  # Deactivated for 'Pure Sniper' (Let trades breathe)
# En Footprint scalping, una vez alcanzado el 0.20% (66% del TP esperado),
# iniciamos el trailing a una distancia de 0.08% para asegurar ganancias pero dar más aire.
TRAILING_STOP_ACTIVATION_PCT = (
    0.0025  # Profit threshold (0.25%) before SL starts trailing (Phase 900 R11: raised to clear base tier fees)
)
TRAILING_STOP_DISTANCE_PCT = 0.0015  # 0.15% trailing distance (reverted from R12 tightening, R10 best config)

# --- ATR-Based Dynamic Exits (Phase 710) ---
# Multipliers used to calculate dynamic distances: Distance = Multiplier * ATR
EXIT_ATR_MULT_TS = 3.5  # Increased from 2.5 to 3.5 to allow more breathing room in Defensive Phase
EXIT_ATR_MULT_BE = 3.0  # Increased from 2.0 to 3.0

# --- Phase 800: "Winner Catcher" Expansion ---
# Threshold to transition from Defensive (Phase 0) to Expansion (Phase 1)
TRAILING_STOP_EXPANSION_THRESHOLD_PCT = 0.0035  # Lowered from 0.45% to 0.35%
TRAILING_STOP_EXPANSION_MULT = 7.5  # Widened from 4.5x to 7.5x for structural trend capture
EXPANSION_TP_RR = 6.0  # Ambitious 6:1 target for the expansion phase

# --- Breakeven ---
# Move SL to entry price to secure risk-free trade once a target is reached.
BREAKEVEN_ENABLED = False  # Deactivated for 'Pure Sniper' (Structural Anchors only)
BREAKEVEN_ACTIVATION_PCT = 0.0025  # Loosened from 0.15% to 0.25%

# --- Signal Reversal ---
# Close position if a strong opposite signal is detected from consensus.
SIGNAL_REVERSAL_ENABLED = False  # Deactivated as per user request (threshold mismatch)
SIGNAL_REVERSAL_THRESHOLD = 0.8  # Required confidence (0-1) to trigger an immediate market close
GRACEFUL_SL_TIMEOUT = 10.0  # Seconds to wait for SL modification before considering it a failure

# --- Phase 660: Trend Gating ---
OTF_STRICT_LOCK = True  # If True, prohibits fading strong One-Timeframing trends
VA_EXPANSION_GATING = True  # If True, prohibits shorts when Value is expanding up (Price > VAH & Price > Open)

# --- Setup-Specific Risk/Reward (RR) Ratios (Phase 712) ---
# High-frequency survival math: Minimum RR required to offset fees/slippage per setup.
SETUP_RR_RATIOS = {
    "FootprintTrappedTraders": 1.2,  # Fast reversion - target wick recovery
    "FootprintDeltaDivergence": 2.0,  # Structural reversal - target opposite Value Area
    "FootprintStackedImbalance": 1.5,  # Trend continuation - target previous move extension
    "FootprintPOCRejection": 1.2,  # Local SR test - target internal candle POC
    "DEFAULT": 1.1,  # Survival floor for all trades
}

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
# 🛡️ PORTFOLIO GUARD (Risk Management)
# =====================================================

# Master switch for the guard. When disabled, all checks are skipped.
PORTFOLIO_GUARD_ENABLED = True

# Drawdown velocity (rolling window)
# En scalping, los drawdowns rápidos (flash crashes) deben apagar el bot.
GUARD_CAUTION_DRAWDOWN_PCT = 0.02  # 2% loss → CAUTION (block new entries)
GUARD_CRITICAL_DRAWDOWN_PCT = 0.05  # 5% loss → CRITICAL (drain mode)
GUARD_DRAWDOWN_WINDOW_MINUTES = 10  # Rolling window for drawdown calc

# Loss streak (consecutive losing trades)
GUARD_MAX_CONSECUTIVE_LOSSES = (
    12  # → CRITICAL after N consecutive losses (R13: raised high to prevent early cascade lock)
)

# Error rate (execution errors in a time window)
GUARD_MAX_ERRORS_WINDOW = 10  # N errors → TERMINAL (emergency shutdown)
GUARD_ERROR_WINDOW_MINUTES = 5

# Solvency: equity * bet_size must be >= min_notional * multiplier
GUARD_SOLVENCY_MULTIPLIER = 1.25

# Sizing violations (order notional < exchange minimum)
GUARD_CAUTION_SIZING_VIOLATIONS = 1  # 1 violation → CAUTION
GUARD_TERMINAL_SIZING_VIOLATIONS = 2  # 2 violations → TERMINAL (Buffer for rounding flutters)

# Recovery cooldown: minimum time in elevated state before allowing recovery
GUARD_RECOVERY_COOLDOWN_SECONDS = 60  # 1 minute (reduced to avoid backtest lockout)


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

# =====================================================
# 🔍 AUDIT & EDGE VALIDATION (Phase 800)
# =====================================================

# Master switch for the Setup Edge Auditor.
# When enabled:
# 1. Records every signal (AggregatedSignalEvent) to DB.
# 2. Samples price trajectory every N seconds.
# 3. Disables proactive exits (Shadow SL, Micro-Exits) for interference-free study.
AUDIT_MODE = False

# How often (in seconds) to sample price after a signal for MFE/MAE tracking.
AUDIT_SAMPLING_FREQ = 1.0  # Sample price every 1.0s

# =====================================================
# 🚀 HFT EXIT MANAGER (Phase 1100 - Axia-Style Patience)
# =====================================================

# Master switch: Enable HFT "Dumb" Exit Manager instead of complex ExitManager (v1).
# Phase 1100: Transitioning from 'Dumb' to 'Axia-Style Professional Invalidation'.
HFT_EXIT_MODE = True

# Mode Toggle: If True, uses setup-specific structural invalidation (Patience).
AXIA_INVALIDATION_ENABLED = False

# Grace Period: Minimum seconds a trade must 'breathe' before any tactical exit allowed.
PATIENCE_LOCK_GRACE_PERIOD = 15.0

# ÚNICA protección en HFT mode: Liquidation prevention.
# Solo interviene si el precio cae más de X% (catastrófico).
CATASTROPHIC_STOP_PCT = 0.50  # 50% drawdown = true emergency only

# HFT Airbag (Phase 1210 - Tactical Silence):
# Closes position if order flow becomes toxic (extreme Z-Score).
HFT_AIRBAG_ENABLED = False
HFT_TOXIC_FLOW_THRESHOLD = 4.5  # Standard: 4.5 (Patience limit)
HFT_WALL_COLLAPSE_THRESHOLD = 0.15  # Skewness < 0.15 means our wall vanished

# Legacy ExitManager features (ignored when HFT_EXIT_MODE = True):
SHADOW_SL_ENABLED = False
SHADOW_BREAKEVEN_ENABLED = False
SHADOW_TRAILING_ENABLED = False
TACTICAL_AIRBAG_ENABLED = False
TIME_BASED_EXIT_ENABLED = False
SIGNAL_REVERSAL_ENABLED = False
