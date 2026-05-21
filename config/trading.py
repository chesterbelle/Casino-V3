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
PORTFOLIO_GUARD_ENABLED = False

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

# Phase 1850: Decision Trace Infrastructure (Capa de Hierro)
# If True, records detailed accept/reject reasons for every potential signal.
# Routed asynchronously to avoid HFT latency impact.
ENABLE_DECISION_TRACE = False

# How often (in seconds) to sample price after a signal for MFE/MAE tracking.
AUDIT_SAMPLING_FREQ = 30.0  # Sample price every 30.0s (30x faster backtests)

# Max holding emitted by SetupEngine for absorption scenarios (seconds).
# Aligned with setup_edge_auditor DEFAULT_WINDOW (4h) and generalized-edge-audit 2026-05-21.
ABSORPTION_MAX_HOLDING_SEC = 14400

# =====================================================
# 🏹 LIMIT SNIPER (V6-Limit)
# =====================================================

# Master switch: Enable Limit Sniper mode (Maker entries)
# When False, the bot uses traditional Market (Taker) orders.
LIMIT_SNIPER_ENABLED = False  # Set to False to use Market (Taker) entries for quality iteration

# --- DYNAMIC SNIPER (Chase Logic) ---
# Phase 1201: Active Maker-Optimization
LIMIT_SNIPER_CHASE_ENABLED = True
LIMIT_SNIPER_MAX_CHASE_ATTEMPTS = 3  # How many times to re-price before giving up
LIMIT_SNIPER_TIMEOUT_MS = 5000  # 5 seconds max for sniper to work
LIMIT_SNIPER_CHECK_INTERVAL_MS = 100  # Polling interval for book/status

# Front-Running Offset: Distance (in % decimal) to place the LIMIT order ahead of the level.
# E.g., 0.0004 = 0.04% ahead. This significantly improves fill rate in fast reversals.
LIMIT_SNIPER_OFFSET_PCT = 0.0004

# Micro-Canceller Window: Time (in seconds) to wait for tactical confirmation
# before pulling the LIMIT order from the book.
LIMIT_SNIPER_CONFIRM_WINDOW_SEC = 0.50

# Sniper-Fill Reality (Backtest only): If True, VirtualExchange requires
# price to strictly CROSS the level (price > limit + 1 tick) to fill.
LIMIT_SNIPER_BACKTEST_STRICT_FILL = False  # Touch-fill (signal fires at level)

# =====================================================
# 🎯 SLIM EXIT ENGINE (V10.2 - Asset-Specific 4-Pillars)
# =====================================================

# Master Switch for the new Slim Engine
SLIM_EXIT_ACTIVE = True

ASSET_EXIT_PROFILES = {
    "BLUE_CHIP": {
        "assets": ["BTC/USDT", "ETH/USDT"],
        "scale_out": {"enabled": True, "at_atr": 2.5, "fraction": 0.3},
        "break_even": {"enabled": True, "at_atr": 2.5, "offset_ticks": 2},
        "trailing": {"enabled": True, "distance_atr": 5.0, "activation_atr": 4.0},
        "delta_invalidation": {"enabled": True, "z_score_threshold": 5.5},
        "execution_strategy": "MAKER_PASSIVE",
    },
    "LIQUID_ALT": {
        "assets": ["LTC/USDT", "XRP/USDT", "BCH/USDT", "LINK/USDT"],
        "scale_out": {"enabled": False, "at_atr": 1.5, "fraction": 0.5},
        "break_even": {"enabled": False, "at_atr": 2.0, "offset_ticks": 1},
        "trailing": {"enabled": False, "distance_atr": 4.0, "activation_atr": 3.0},
        "delta_invalidation": {"enabled": False, "z_score_threshold": 4.5},
        "execution_strategy": "MAKER_JOIN",
    },
    "HIGH_BETA": {
        "assets": ["SOL/USDT", "AVAX/USDT", "DOT/USDT"],
        "scale_out": {"enabled": True, "at_atr": 1.8, "fraction": 0.5},
        "break_even": {"enabled": True, "at_atr": 2.0, "offset_ticks": 1},
        "trailing": {"enabled": True, "distance_atr": 4.5, "activation_atr": 3.5},
        "delta_invalidation": {"enabled": True, "z_score_threshold": 5.0},
        "execution_strategy": "MAKER_JOIN",
    },
    "DEFAULT": {
        "scale_out": {"enabled": False, "at_atr": 1.5, "fraction": 0.5},
        "break_even": {"enabled": False, "at_atr": 2.0, "offset_ticks": 1},
        "trailing": {"enabled": False, "distance_atr": 4.0, "activation_atr": 3.0},
        "delta_invalidation": {"enabled": False, "z_score_threshold": 4.5},
        "execution_strategy": "MAKER_JOIN",
    },
}

# -----------------------------------------------------
# GLOBAL EXIT SETTINGS
# -----------------------------------------------------
# Grace Period: Minimum seconds a trade must 'breathe' before any tactical exit allowed.
PATIENCE_LOCK_GRACE_PERIOD = 15.0
# Seconds to wait for SL/TP modification before considering it a failure
GRACEFUL_SL_TIMEOUT = 10.0
GRACEFUL_TP_TIMEOUT = 10.0

# Legacy compatibility (kept for any external references, but ignored by SlimExitEngine)
HFT_EXIT_MODE = True
SIGNAL_REVERSAL_ENABLED = False
