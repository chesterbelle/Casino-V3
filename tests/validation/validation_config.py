"""
Configuración común para validación de Testing vs Backtesting.

Este archivo define los parámetros compartidos entre:
- Testing en vivo (test_live_60_candles.py)
- Backtesting (test_backtest_60_candles.py)
- Comparación (compare_testing_vs_backtest.py)
"""

from typing import Any, Dict

# =========================================================
# CONFIGURACIÓN DE LA PRUEBA
# =========================================================

COMMON_CONFIG: Dict[str, Any] = {
    # Exchange y símbolo
    "exchange": "kraken",
    "symbol": "BTC/USD:USD",
    "timeframe": "1m",
    # Duración de la prueba
    "num_candles": 60,  # 60 velas de 1 minuto = 1 hora
    # Balance inicial
    "initial_balance": 10000.0,  # USD
    # Estrategia a usar
    "strategy": "SimpleMovingAverageCrossover",  # Cambiar según estrategia
    # Parámetros de la estrategia
    "strategy_params": {
        "fast_period": 5,
        "slow_period": 20,
        "tp_percent": 0.005,  # 0.5% take profit
        "sl_percent": 0.003,  # 0.3% stop loss
        "position_size": 0.001,  # BTC por operación
    },
}

# =========================================================
# TOLERANCIAS PARA COMPARACIÓN
# =========================================================

TOLERANCES: Dict[str, float] = {
    # Diferencia aceptable en precios (por slippage)
    "price_difference_percent": 0.001,  # 0.1%
    # Diferencia aceptable en balance final
    "balance_difference_percent": 0.001,  # 0.1%
    # Diferencia aceptable en timing (segundos)
    "timing_difference_seconds": 5,
    # Diferencia aceptable en PnL por operación
    "pnl_difference_percent": 0.01,  # 1%
    # Diferencia aceptable en métricas (win rate, etc.)
    "metrics_difference_percent": 0.01,  # 1%
}

# =========================================================
# RUTAS DE ARCHIVOS
# =========================================================

import os
from datetime import datetime

# Directorio base para resultados
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tests", "validation_results")


def get_timestamp_str() -> str:
    """Genera timestamp para nombres de archivo."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_live_results_path(timestamp: str = None) -> str:
    """Path para resultados de testing en vivo."""
    if timestamp is None:
        timestamp = get_timestamp_str()
    return os.path.join(RESULTS_DIR, f"test_live_results_{timestamp}.json")


def get_historical_data_path(timestamp: str = None) -> str:
    """Path para datos históricos descargados."""
    if timestamp is None:
        timestamp = get_timestamp_str()
    return os.path.join(RESULTS_DIR, f"historical_data_{timestamp}.json")


def get_backtest_results_path(timestamp: str = None) -> str:
    """Path para resultados de backtesting."""
    if timestamp is None:
        timestamp = get_timestamp_str()
    return os.path.join(RESULTS_DIR, f"test_backtest_results_{timestamp}.json")


def get_comparison_report_path(timestamp: str = None) -> str:
    """Path para reporte de comparación."""
    if timestamp is None:
        timestamp = get_timestamp_str()
    return os.path.join(RESULTS_DIR, f"comparison_report_{timestamp}.txt")


# =========================================================
# FORMATO DE DATOS
# =========================================================

# Estructura de datos para resultados
RESULTS_SCHEMA = {
    "test_info": {
        "exchange": str,
        "symbol": str,
        "timeframe": str,
        "start_time": str,  # ISO format
        "end_time": str,  # ISO format
        "initial_balance": float,
        "final_balance": float,
        "mode": str,  # "live" o "backtest"
    },
    "candles": [
        {
            "timestamp": int,  # Unix timestamp en ms
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float,
        }
    ],
    "signals": [
        {
            "timestamp": int,
            "candle_index": int,
            "signal": str,  # "LONG", "SHORT", "CLOSE"
            "confidence": float,
            "indicators": dict,  # Valores de indicadores
        }
    ],
    "orders": [
        {
            "timestamp": int,
            "candle_index": int,
            "order_id": str,
            "side": str,  # "buy", "sell"
            "amount": float,
            "entry_price": float,
            "exit_price": float,  # None si aún abierta
            "tp_price": float,
            "sl_price": float,
            "status": str,  # "open", "filled", "closed"
            "close_reason": str,  # "tp", "sl", "manual", None
            "pnl": float,  # None si aún abierta
            "fees": float,
        }
    ],
    "balance_history": [
        {
            "timestamp": int,
            "candle_index": int,
            "balance": float,
            "equity": float,  # Balance + unrealized PnL
        }
    ],
    "metrics": {
        "total_trades": int,
        "winning_trades": int,
        "losing_trades": int,
        "win_rate": float,
        "total_pnl": float,
        "total_fees": float,
        "net_pnl": float,
        "max_drawdown": float,
        "max_drawdown_percent": float,
        "sharpe_ratio": float,
        "profit_factor": float,
    },
}

# =========================================================
# UTILIDADES
# =========================================================


def ensure_results_dir():
    """Asegura que el directorio de resultados existe."""
    os.makedirs(RESULTS_DIR, exist_ok=True)


def validate_config():
    """Valida que la configuración es correcta."""
    required_keys = ["exchange", "symbol", "timeframe", "num_candles", "initial_balance"]
    for key in required_keys:
        if key not in COMMON_CONFIG:
            raise ValueError(f"Falta clave requerida en COMMON_CONFIG: {key}")

    if COMMON_CONFIG["num_candles"] <= 0:
        raise ValueError("num_candles debe ser mayor que 0")

    if COMMON_CONFIG["initial_balance"] <= 0:
        raise ValueError("initial_balance debe ser mayor que 0")

    return True


# Validar configuración al importar
validate_config()
ensure_results_dir()
