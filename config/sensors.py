"""
====================================================
🎛️ CONFIGURACIÓN DE SENSORES — CASINO V3 (Absorption Scalping V1)
====================================================

Configuración de detectores de Orderflow de Alta Frecuencia.

Phase 7: LTA V4/V5/V6 PURGED - Absorption V1 is the sole strategy.
"""

# =====================================================
# 🎛️ SENSORES ACTIVOS ROOT
# =====================================================

ACTIVE_SENSORS = {
    # === CONTEXT SENSORS (Required for structural levels and regime detection) ===
    "MarketRegime": True,  # 3-layer anticipatory regime detection
    "SessionValueArea": True,  # Structural levels (POC, VAH, VAL, IB)
    # === ABSORPTION V1: Main-process only (not in workers) ===
    # AbsorptionDetector runs directly in SetupEngine.on_candle_absorption
}

# =====================================================
# ⏱️ TIMEFRAME BASE
# =====================================================

SENSOR_TIMEFRAMES = {
    "MarketRegime": ["1m"],
    "SessionValueArea": ["1m"],
    "AbsorptionDetector": ["1m"],
}

# =====================================================
# ⚙️ PARÁMETROS BASE
# =====================================================

SENSOR_PARAMS = {
    "MarketRegime": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Context sensor
    },
    "SessionValueArea": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Context sensor
    },
    "AbsorptionDetector": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # TP/SL calculated dynamically in AbsorptionSetupEngine
    },
    # === DEFAULT FALLBACK ===
    "_default": {
        "1m": {"tp_pct": 0.50, "sl_pct": 0.30},
    },
}

# =====================================================
# 🔧 HELPER FUNCTIONS
# =====================================================


def get_sensor_params(sensor_id: str, timeframe: str = "1m") -> dict:
    params_ref = None
    if sensor_id not in SENSOR_PARAMS:
        params_ref = SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.0015, "sl_pct": 0.0010})
    else:
        sensor_config = SENSOR_PARAMS[sensor_id]
        if isinstance(sensor_config, dict):
            if timeframe in sensor_config:
                params_ref = sensor_config[timeframe]
            elif "tp_pct" in sensor_config:
                params_ref = sensor_config
            else:
                tf_keys = [k for k in sensor_config.keys() if k in ("1m")]
                if tf_keys:
                    params_ref = sensor_config[tf_keys[0]]
                else:
                    params_ref = SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.0015, "sl_pct": 0.0010})
        else:
            params_ref = SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.0015, "sl_pct": 0.0010})

    if not params_ref:
        params_ref = SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.0015, "sl_pct": 0.0010})

    params = params_ref.copy()

    # Native Fast-Track Override: Make sensors highly radioactive
    import sys

    if "--fast-track" in sys.argv:
        if "min_score_long" in params:
            params["min_score_long"] = 0.10
        if "min_score_short" in params:
            params["min_score_short"] = 0.10

    return params


def get_sensor_timeframe(sensor_id: str) -> str:
    tfs = get_sensor_timeframes(sensor_id)
    return tfs[0] if tfs else "1m"


def get_sensor_timeframes(sensor_id: str) -> list:
    tfs = SENSOR_TIMEFRAMES.get(sensor_id, ["1m"])
    if isinstance(tfs, str):
        return [tfs]
    return list(tfs)
