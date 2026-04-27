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
    # Phase 2100: MarketRegime replaces OneTimeframing with 3-layer anticipatory detection.
    # OneTimeframing is kept as fallback (disabled by default when MarketRegime is active).
    "MarketRegime": True,
    "OneTimeframing": False,  # Legacy — superseded by MarketRegime
    "BigOrderSensor": True,
    "SessionValueArea": True,
    "FootprintDeltaVelocity": True,
    "MicroStructureContext": True,
    "LiquidationCascade": True,
    "VolatilitySpike": False,
    # === LTA V5: NEW SENSORS (Phase 3: Redesigned with correct concepts) ===
    "TacticalPoorExtreme": False,  # DEPRECATED: Concept was incorrect
    "TacticalSinglePrintReversion": True,  # CERTIFIED: Passed audit
    "TacticalVolumeClimaxReversion": True,  # AUDIT MODE: Testing now
    # === ABSORPTION V1: NEW SENSORS (Phase 2.2) ===
    "AbsorptionDetector": False,  # Phase 2.2: Real-time absorption detection (TESTING)
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
    "MarketRegime": ["1m"],  # Phase 2100: 3-layer anticipatory regime sensor
    "OneTimeframing": ["1m"],  # Legacy fallback
    "BigOrderSensor": ["1m"],
    "SessionValueArea": ["1m"],
    "FootprintDeltaVelocity": ["1m"],
    "MicroStructureContext": ["1m"],
    "LiquidationCascade": ["1m"],
    "VolatilitySpike": ["1m"],
    # LTA V5: New sensors
    "TacticalPoorExtreme": ["1m"],  # Deprecated
    "TacticalSinglePrintReversion": ["1m"],  # Redesigned
    "TacticalVolumeClimaxReversion": ["1m"],
    # Absorption V1: New sensors
    "AbsorptionDetector": ["1m"],  # Phase 2.2: Real-time absorption detection
}

# =====================================================
# ⚙️ PARÁMETROS BASE (Micro-Scalping Targets)
# =====================================================
# TP / SL orientados a tomar 0.1% a 0.2% del volumen institucional

SENSOR_PARAMS = {
    "FootprintImbalance": {
        "1m": {"tp_pct": 0.50, "sl_pct": 0.30, "min_score_long": 0.85},
    },
    "FootprintAbsorption": {
        "1m": {"tp_pct": 0.60, "sl_pct": 0.35, "min_score_long": 0.85},
    },
    "FootprintPOCRejection": {
        "1m": {"tp_pct": 0.65, "sl_pct": 0.35, "min_score_long": 0.85},
    },
    "FootprintDeltaDivergence": {
        "1m": {"tp_pct": 0.55, "sl_pct": 0.30, "min_score_long": 0.85},
    },
    "FootprintStackedImbalance": {
        "1m": {"tp_pct": 0.55, "sl_pct": 0.30, "min_score_long": 0.85},
    },
    "FootprintTrappedTraders": {
        "1m": {"tp_pct": 0.70, "sl_pct": 0.40, "min_score_long": 0.85},
    },
    "FootprintVolumeExhaustion": {
        "1m": {"tp_pct": 0.45, "sl_pct": 0.25, "min_score_long": 0.85},
    },
    "FootprintDeltaPoCShift": {
        "1m": {"tp_pct": 0.50, "sl_pct": 0.30, "min_score_long": 0.85},
    },
    "CumulativeDelta": {
        "1m": {"tp_pct": 0.50, "sl_pct": 0.30, "min_score_long": 0.85},
    },
    "BigOrderSensor": {
        "1m": {"tp_pct": 0.70, "sl_pct": 0.40, "min_score_long": 0.85},
    },
    "SessionValueArea": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},
    },
    "FootprintDeltaVelocity": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},
    },
    "OneTimeframing": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Context sensor, no TP/SL needed
    },
    "MarketRegime": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Phase 2100: Context sensor, no TP/SL needed
    },
    "MicroStructureContext": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Context sensor, no TP/SL needed
    },
    "LiquidationCascade": {
        "1m": {"tp_pct": 0.80, "sl_pct": 0.40, "min_score_long": 0.85},
    },
    # LTA V5: New sensors (conservative params until audit)
    "TacticalPoorExtreme": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Deprecated
    },
    "TacticalSinglePrintReversion": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Tactical signal, no direct TP/SL
    },
    "TacticalVolumeClimaxReversion": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Tactical signal, no direct TP/SL
    },
    # Absorption V1: New sensors (Phase 2.2)
    "AbsorptionDetector": {
        "1m": {"tp_pct": 0.0, "sl_pct": 0.0},  # Tactical signal, TP/SL calculated dynamically in SetupEngine
    },
    # "VolatilitySpike": {
    #     "1m": {"tp_pct": 0.50, "sl_pct": 0.30},
    # },
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
