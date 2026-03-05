"""
====================================================
🎛️ CONFIGURACIÓN DE SENSORES — CASINO V3 (Phase 400 - Footprint Scalping)
====================================================

Configuración de detectores de Orderflow de Alta Frecuencia.
"""

# =====================================================
# 🎛️ SENSORES ACTIVOS ROOT
# =====================================================

ACTIVE_SENSORS = {
    # === DEBUG ===
    "DebugHeartbeat": False,
    # === FOOTPRINT SCALPING (Tick/Orderbook Reactive) ===
    "FootprintImbalance": True,
    "FootprintAbsorption": True,
    "FootprintPOCRejection": True,
    "FootprintDeltaDivergence": True,
    "FootprintStackedImbalance": True,
    "FootprintTrappedTraders": True,
    "FootprintVolumeExhaustion": True,
    "FootprintDeltaPoCShift": True,
    "CumulativeDelta": True,
    "OneTimeframing": True,
    "BigOrderSensor": True,
    "SessionValueArea": True,
}

# =====================================================
# ⏱️ TIMEFRAME BASE
# =====================================================
# En footprint scalping la matriz de memoria maneja el DOM en tiempo real,
# pero referenciamos temporales de "1m" para alinear logs de agregación.

SENSOR_TIMEFRAMES = {
    "FootprintImbalance": ["1m"],
    "FootprintAbsorption": ["1m"],
    "FootprintPOCRejection": ["1m"],
    "FootprintDeltaDivergence": ["1m"],
    "FootprintStackedImbalance": ["1m"],
    "FootprintTrappedTraders": ["1m"],
    "FootprintVolumeExhaustion": ["1m"],
    "FootprintDeltaPoCShift": ["1m"],
    "CumulativeDelta": ["1m"],
    "OneTimeframing": ["1m"],
    "BigOrderSensor": ["1m"],
    "SessionValueArea": ["1m"],
}

# =====================================================
# ⚙️ PARÁMETROS BASE (Micro-Scalping Targets)
# =====================================================
# TP / SL orientados a tomar 0.1% a 0.2% del volumen institucional

SENSOR_PARAMS = {
    "FootprintImbalance": {
        "1m": {"tp_pct": 0.25, "sl_pct": 0.15, "min_score_long": 0.85},
    },
    "FootprintAbsorption": {
        "1m": {"tp_pct": 0.30, "sl_pct": 0.20, "min_score_long": 0.85},
    },
    "FootprintPOCRejection": {
        "1m": {"tp_pct": 0.35, "sl_pct": 0.20, "min_score_long": 0.85},
    },
    "FootprintDeltaDivergence": {
        "1m": {"tp_pct": 0.30, "sl_pct": 0.20, "min_score_long": 0.85},
    },
    "FootprintStackedImbalance": {
        "1m": {"tp_pct": 0.30, "sl_pct": 0.20, "min_score_long": 0.85},
    },
    "FootprintTrappedTraders": {
        "1m": {"tp_pct": 0.40, "sl_pct": 0.25, "min_score_long": 0.85},
    },
    "FootprintVolumeExhaustion": {
        "1m": {"tp_pct": 0.15, "sl_pct": 0.10, "min_score_long": 0.85},
    },
    "FootprintDeltaPoCShift": {
        "1m": {"tp_pct": 0.20, "sl_pct": 0.15, "min_score_long": 0.85},
    },
    "CumulativeDelta": {
        "1m": {"tp_pct": 0.25, "sl_pct": 0.15, "min_score_long": 0.85},
    },
    "BigOrderSensor": {
        "1m": {"tp_pct": 0.35, "sl_pct": 0.20, "min_score_long": 0.85},
    },
    "SessionValueArea": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},
    },
    "OneTimeframing": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Context sensor, no TP/SL needed
    },
    # === DEFAULT FALLBACK ===
    "_default": {
        "1m": {"tp_pct": 0.20, "sl_pct": 0.15},
    },
}

# =====================================================
# 🔧 HELPER FUNCTIONS
# =====================================================


def get_sensor_params(sensor_id: str, timeframe: str = "1m") -> dict:
    if sensor_id not in SENSOR_PARAMS:
        return SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.0015, "sl_pct": 0.0010})

    sensor_config = SENSOR_PARAMS[sensor_id]
    if isinstance(sensor_config, dict):
        if timeframe in sensor_config:
            return sensor_config[timeframe]
        if "tp_pct" in sensor_config:
            return sensor_config
        tf_keys = [k for k in sensor_config.keys() if k in ("1m")]
        if tf_keys:
            return sensor_config[tf_keys[0]]

    return SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.0015, "sl_pct": 0.0010})


def get_sensor_timeframe(sensor_id: str) -> str:
    tfs = get_sensor_timeframes(sensor_id)
    return tfs[0] if tfs else "1m"


def get_sensor_timeframes(sensor_id: str) -> list:
    tfs = SENSOR_TIMEFRAMES.get(sensor_id, ["1m"])
    if isinstance(tfs, str):
        return [tfs]
    return list(tfs)
