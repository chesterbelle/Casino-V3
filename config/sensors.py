"""
====================================================
🎛️ CONFIGURACIÓN DE SENSORES — CASINO V2
====================================================

Configuración de detectores técnicos y sus parámetros.
"""

import json
from pathlib import Path

# =====================================================
# 🎛️ SENSORES ACTIVOS
# =====================================================

ACTIVE_SENSORS = {
    # === DEBUG ===
    "DebugHeartbeat": False,
    # === OPTIMIZED SENSORS (2025-11-29) ===
    "ADXFilter": True,
    "BollingerSqueeze": True,
    "BollingerTouch": True,
    "CCIReversion": True,
    "DecelerationCandles": True,
    "DojiIndecision": True,
    "EMA50Support": True,
    "EMACrossover": True,
    "EngulfingPattern": True,
    "ExtremeCandleRatio": True,
    "FVGRetest": True,
    "InsideBarBreakout": True,
    "KeltnerReversion": True,
    "MACDCrossover": True,
    "MarubozuMomentum": True,
    "MomentumBurst": True,
    "MorningStar": True,
    "PinBarReversal": True,
    "RSIReversion": True,
    "RailsPattern": True,
    "StochasticReversion": True,
    "Supertrend": True,
    "VCPPattern": True,
    "VWAPDeviation": True,
    "VolumeImbalance": True,
    "WilliamsRReversion": True,
    "ZScoreReversion": True,
    # === FOOTPRINT SENSORS (New) ===
    "FootprintImbalance": True,
    "FootprintAbsorption": True,
    "FootprintPOCRejection": True,
    "FootprintDeltaDivergence": True,
    "FootprintStackedImbalance": True,
    "FootprintTrappedTraders": True,
    "FootprintVolumeExhaustion": True,
    "FootprintDeltaPoCShift": True,
    # === QUICKSCALPER SENSORS (Active for demo) ===
    "Fakeout": True,
    "MicroTrend": True,
    "SmartRange": True,
    "AdaptiveRSI": True,
    "HigherTFTrend": True,  # Context sensor
    # === ALL SENSORS ENABLED FOR DEBUGALL ===
    "OrderBlock": True,
    "VWAPBreakout": True,
    "VWAPMomentum": True,
    "MTFImpulse": True,
    "VolatilityWakeup": True,
    "BollingerRejection": True,
    "KeltnerBreakout": True,
    "HurstRegime": True,
    "VSAReversal": True,
    "ThreeBar": True,
    "TweezerPattern": True,
    "SupportResistance": True,
    "VolumeSpike": True,
    "LiquidityVoid": True,
    "LongTail": True,
    "WyckoffSpring": True,
    "AbsorptionBlock": True,
    "ParabolicSAR": True,
    "WickRejection": True,
    # === NEW STRUCTURAL SENSORS ===
    "NarrowRange7": True,
    "ConsecutiveCandles": True,
    "RangeExpansion": True,
    "ThreeWhiteSoldiers": True,
    "ThreeBlackCrows": True,
    "WideRangeBar": True,
    "DoubleBottom": True,
    "DoubleTop": True,
    "HigherHighsLowerLows": True,
    "IslandReversal": True,
}


# =====================================================
# ⏱️ TIMEFRAME ÓPTIMO POR SENSOR
# =====================================================
# Define qué timeframe del context usar para cada sensor
# Basado en la lógica del sensor y recomendaciones de trading algorítmico:
# - Patrones de velas: 15m/1h (menor ruido)
# - Osciladores: 5m/15m (balance señal/ruido)
# - Momentum/Trend: 1h/4h (contexto macro)
# - Ejecución rápida: 1m (precisión de entrada)

SENSOR_TIMEFRAMES = {
    # =========================================================
    # 🎯 MTF CONFIGURATION - All sensors now monitor 2-3 TFs
    # =========================================================
    # Format: ["fast", "medium", "slow"] for optimization
    # The optimizer will find the best TF + TP/SL combo per sensor
    #
    # === TREND INDICATORS ===
    "ADXFilter": ["5m", "15m", "1h"],
    "EMACrossover": ["5m", "15m", "1h"],
    "MACDCrossover": ["5m", "15m", "1h"],
    "Supertrend": ["5m", "15m", "1h"],
    "ParabolicSAR": ["5m", "15m", "1h"],
    "HigherTFTrend": ["15m", "1h"],  # Macro context only
    "MTFImpulse": ["5m", "15m"],
    "EMA50Support": ["5m", "15m", "1h"],
    #
    # === OSCILLATORS ===
    "RSIReversion": ["1m", "5m", "15m"],
    "StochasticReversion": ["1m", "5m", "15m"],
    "CCIReversion": ["1m", "5m", "15m"],
    "WilliamsRReversion": ["1m", "5m", "15m"],
    "AdaptiveRSI": ["5m", "15m"],
    #
    # === VOLATILITY BANDS ===
    "BollingerTouch": ["1m", "5m", "15m"],
    "BollingerSqueeze": ["5m", "15m"],
    "BollingerRejection": ["5m", "15m"],
    "KeltnerReversion": ["1m", "5m", "15m"],
    "KeltnerBreakout": ["5m", "15m"],
    "ZScoreReversion": ["1m", "5m", "15m"],
    #
    # === CANDLESTICK PATTERNS ===
    "EngulfingPattern": ["1m", "5m", "15m"],
    "PinBarReversal": ["1m", "5m", "15m"],
    "RailsPattern": ["5m", "15m"],
    "MorningStar": ["5m", "15m"],
    "DojiIndecision": ["1m", "5m", "15m"],
    "TweezerPattern": ["5m", "15m"],
    "ThreeBar": ["5m", "15m"],
    "MarubozuMomentum": ["5m", "15m"],
    "WickRejection": ["1m", "5m", "15m"],
    "LongTail": ["1m", "5m", "15m"],
    #
    # === STRUCTURAL PATTERNS ===
    "VCPPattern": ["5m", "15m"],
    "InsideBarBreakout": ["1m", "5m", "15m"],
    "DecelerationCandles": ["5m", "15m"],
    "ExtremeCandleRatio": ["1m", "5m", "15m"],
    "Fakeout": ["5m", "15m"],
    #
    # === VOLUME ANALYSIS ===
    "VolumeImbalance": ["5m", "15m"],
    "VolumeSpike": ["1m", "5m", "15m"],
    "VSAReversal": ["1m", "5m", "15m"],
    "AbsorptionBlock": ["1m", "5m", "15m"],
    #
    # === FOOTPRINT SENSORS ===
    "FootprintImbalance": ["1m"],
    "FootprintAbsorption": ["1m"],
    "FootprintPOCRejection": ["1m"],
    "FootprintDeltaDivergence": ["1m"],
    "FootprintStackedImbalance": ["1m"],
    "FootprintTrappedTraders": ["1m"],
    "FootprintVolumeExhaustion": ["1m"],
    "FootprintDeltaPoCShift": ["1m"],
    #
    # === SMART MONEY CONCEPTS ===
    "OrderBlock": ["5m", "15m"],
    "LiquidityVoid": ["5m", "15m"],
    "FVGRetest": ["5m", "15m"],
    "WyckoffSpring": ["5m", "15m"],
    #
    # === MOMENTUM ===
    "MomentumBurst": ["1m", "5m", "15m"],
    "MicroTrend": ["1m", "5m"],
    "SmartRange": ["1m", "5m"],
    #
    # === VWAP ===
    "VWAPDeviation": ["1m", "5m"],
    "VWAPBreakout": ["5m", "15m"],
    "VWAPMomentum": ["1m", "5m"],
    #
    # === REGIME DETECTION ===
    "HurstRegime": ["5m", "15m"],
    "VolatilityWakeup": ["5m", "15m"],
    "SupportResistance": ["5m", "15m"],
    # === NEW STRUCTURAL SENSORS ===
    "NarrowRange7": ["5m", "15m"],
    "ConsecutiveCandles": ["1m", "5m", "15m"],
    "RangeExpansion": ["1m", "5m", "15m"],
    "ThreeWhiteSoldiers": ["5m", "15m"],
    "ThreeBlackCrows": ["5m", "15m"],
    "WideRangeBar": ["1m", "5m", "15m"],
    "DoubleBottom": ["5m", "15m", "1h"],
    "DoubleTop": ["5m", "15m", "1h"],
    "HigherHighsLowerLows": ["5m", "15m"],
    "IslandReversal": ["5m", "15m"],
}


# =====================================================
# ⚙️ PARÁMETROS DE SENSORES (MTF OPTIMIZED 2025-12-04)
# =====================================================
# Grid search optimizado sobre 90d 1m / 30d 5m / 30d 15m
# Cada sensor tiene TP/SL para su TF óptimo
# Format: "SensorName": {"tf": {"tp_pct": X, "sl_pct": Y}}

SENSOR_PARAMS = {
    # === TOP PERFORMERS (Exp > 0.5%) ===
    "MorningStar": {
        "15m": {"tp_pct": 0.1500, "sl_pct": 0.0250},  # Exp: 1.730% ⭐ BEST
    },
    "BollingerSqueeze": {
        "15m": {"tp_pct": 0.1500, "sl_pct": 0.0400},  # Exp: 1.515%
    },
    "MomentumBurst": {
        "15m": {"tp_pct": 0.0550, "sl_pct": 0.0950},  # Exp: 1.213%
    },
    "WyckoffSpring": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0200},  # Exp: 0.839%
    },
    "KeltnerBreakout": {
        "15m": {"tp_pct": 0.0750, "sl_pct": 0.0550},  # Exp: 0.820%
    },
    "VolumeSpike": {
        "5m": {"tp_pct": 0.1160, "sl_pct": 0.0680},  # Exp: 0.818%
    },
    "VolatilityWakeup": {
        "15m": {"tp_pct": 0.0600, "sl_pct": 0.0950},  # Exp: 0.761%
    },
    "Supertrend": {
        "15m": {"tp_pct": 0.1150, "sl_pct": 0.0400},  # Exp: 0.680%
    },
    "RailsPattern": {
        "15m": {"tp_pct": 0.1250, "sl_pct": 0.0200},  # Exp: 0.663%
    },
    "VolumeImbalance": {
        "15m": {"tp_pct": 0.1350, "sl_pct": 0.0550},  # Exp: 0.652%
    },
    "ThreeBar": {
        "15m": {"tp_pct": 0.1000, "sl_pct": 0.0250},  # Exp: 0.629%
    },
    "BollingerRejection": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0250},  # Exp: 0.603%
    },
    "EMACrossover": {
        "15m": {"tp_pct": 0.0600, "sl_pct": 0.0800},  # Exp: 0.572%
    },
    "HigherTFTrend": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0500},  # Exp: 0.535%
    },
    "BollingerTouch": {
        "15m": {"tp_pct": 0.0950, "sl_pct": 0.0200},  # Exp: 0.508%
        "5m": {"tp_pct": 0.0770, "sl_pct": 0.0330},  # Exp: 0.492%
    },
    # === GOOD PERFORMERS (Exp 0.2% - 0.5%) ===
    "VWAPDeviation": {
        "1m": {"tp_pct": 0.0970, "sl_pct": 0.0590},  # Exp: 0.500%
    },
    "EMA50Support": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0250},  # Exp: 0.444%
    },
    "ADXFilter": {
        "15m": {"tp_pct": 0.0750, "sl_pct": 0.0900},  # Exp: 0.404%
    },
    "VWAPMomentum": {
        "15m": {"tp_pct": 0.1100, "sl_pct": 0.0300},  # Exp: 0.375%
    },
    "PinBarReversal": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0250},  # Exp: 0.371%
    },
    "MTFImpulse": {
        "15m": {"tp_pct": 0.1200, "sl_pct": 0.0500},  # Exp: 0.351%
    },
    "SupportResistance": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0250},  # Exp: 0.345%
    },
    "FVGRetest": {
        "15m": {"tp_pct": 0.1000, "sl_pct": 0.0500},  # Exp: 0.331%
    },
    "AbsorptionBlock": {
        "5m": {"tp_pct": 0.0320, "sl_pct": 0.0560},  # Exp: 0.329%
    },
    "MarubozuMomentum": {
        "15m": {"tp_pct": 0.1500, "sl_pct": 0.0500},  # Exp: 0.307%
    },
    "ExtremeCandleRatio": {
        "15m": {"tp_pct": 0.1100, "sl_pct": 0.0250},  # Exp: 0.306%
    },
    "MACDCrossover": {
        "15m": {"tp_pct": 0.1000, "sl_pct": 0.0350},  # Exp: 0.286%
    },
    "ZScoreReversion": {
        "15m": {"tp_pct": 0.1350, "sl_pct": 0.0150},  # Exp: 0.277%
    },
    "DojiIndecision": {
        "15m": {"tp_pct": 0.1500, "sl_pct": 0.0550},  # Exp: 0.271%
    },
    "InsideBarBreakout": {
        "15m": {"tp_pct": 0.1250, "sl_pct": 0.0250},  # Exp: 0.256%
    },
    "HurstRegime": {
        "15m": {"tp_pct": 0.1200, "sl_pct": 0.0300},  # Exp: 0.253%
    },
    "TweezerPattern": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0300},  # Exp: 0.247%
    },
    "AdaptiveRSI": {
        "15m": {"tp_pct": 0.1050, "sl_pct": 0.0300},  # Exp: 0.236%
    },
    "KeltnerReversion": {
        "5m": {"tp_pct": 0.0950, "sl_pct": 0.0770},  # Exp: 0.232%
    },
    "VCPPattern": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0250},  # Exp: 0.211%
    },
    # === MODERATE PERFORMERS (Exp 0.05% - 0.2%) ===
    "DecelerationCandles": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0200},  # Exp: 0.172%
    },
    "LongTail": {
        "5m": {"tp_pct": 0.1100, "sl_pct": 0.0110},  # Exp: 0.168%
    },
    "CCIReversion": {
        "15m": {"tp_pct": 0.1350, "sl_pct": 0.0200},  # Exp: 0.141%
    },
    "StochasticReversion": {
        "5m": {"tp_pct": 0.0680, "sl_pct": 0.0800},  # Exp: 0.109%
    },
    "WickRejection": {
        "5m": {"tp_pct": 0.0410, "sl_pct": 0.0770},  # Exp: 0.104%
    },
    "RSIReversion": {
        "15m": {"tp_pct": 0.1300, "sl_pct": 0.0200},  # Exp: 0.095%
    },
    "WilliamsRReversion": {
        "5m": {"tp_pct": 0.0680, "sl_pct": 0.0800},  # Exp: 0.089%
    },
    "SmartRange": {
        "1m": {"tp_pct": 0.0310, "sl_pct": 0.0250},  # Exp: 0.088%
    },
    "MicroTrend": {
        "5m": {"tp_pct": 0.0680, "sl_pct": 0.0530},  # Exp: 0.085%
    },
    "EngulfingPattern": {
        "1m": {"tp_pct": 0.0990, "sl_pct": 0.0110},  # Exp: 0.014%
    },
    "VWAPBreakout": {
        "15m": {"tp_pct": 0.0750, "sl_pct": 0.0300},  # Exp: 0.007%
    },
    # === SENSORS NEEDING MORE DATA ===
    "OrderBlock": {
        "15m": {"tp_pct": 0.1000, "sl_pct": 0.0400},  # Default
    },
    "LiquidityVoid": {
        "15m": {"tp_pct": 0.0800, "sl_pct": 0.0400},  # Default
    },
    "Fakeout": {
        "15m": {"tp_pct": 0.1000, "sl_pct": 0.0400},  # Default
    },
    # === FOOTPRINT SENSORS ===
    "FootprintPOCRejection": {
        "1m": {"tp_pct": 0.0050, "sl_pct": 0.0030},  # Scalping defaults
    },
    "FootprintDeltaDivergence": {
        "1m": {"tp_pct": 0.0050, "sl_pct": 0.0030},
    },
    "FootprintStackedImbalance": {
        "1m": {"tp_pct": 0.0060, "sl_pct": 0.0030},
    },
    "FootprintTrappedTraders": {
        "1m": {"tp_pct": 0.0080, "sl_pct": 0.0040},
    },
    "ParabolicSAR": {
        "15m": {"tp_pct": 0.1000, "sl_pct": 0.0400},  # Default
    },
    # === DEFAULT FALLBACK ===
    "_default": {
        "1m": {"tp_pct": 0.0150, "sl_pct": 0.0100},
        "5m": {"tp_pct": 0.0300, "sl_pct": 0.0200},
        "15m": {"tp_pct": 0.0600, "sl_pct": 0.0400},
        "1h": {"tp_pct": 0.1200, "sl_pct": 0.0800},
    },
}


# =====================================================
# 🔄 LOAD OPTIMIZED PARAMETERS (IF AVAILABLE)
# =====================================================

try:
    optimized_file = Path("config/optimized_params.json")
    if optimized_file.exists():
        with open(optimized_file, "r") as f:
            optimized_data = json.load(f)

        if "sensors" in optimized_data:
            # Update SENSOR_PARAMS with optimized values
            for sensor_name, params in optimized_data["sensors"].items():
                # Handle both single TF and MTF formats
                if "all_timeframes" in params:
                    # MTF format: we need to construct the dict structure
                    # But for now, let's just use the optimal TF params
                    # or merge them properly if SENSOR_PARAMS supports it.
                    # Given current structure, we can just update the entry.

                    # If we want to support multiple TFs, we need to see how
                    # optimize_sensors.py saves it.
                    # It saves: "sensor": {"optimal_timeframe": "15m", "tp_pct": ...}

                    # We need to convert this to SENSOR_PARAMS format:
                    # "Sensor": {"15m": {"tp_pct": ...}}

                    tf = params["optimal_timeframe"]
                    SENSOR_PARAMS[sensor_name] = {tf: {"tp_pct": params["tp_pct"], "sl_pct": params["sl_pct"]}}
                else:
                    # Single TF format (legacy compatible)
                    # "Sensor": {"tp_pct": ..., "sl_pct": ...}
                    # But optimize_sensors.py saves it as flat dict in "sensors"
                    # We need to wrap it in timeframe if possible, or just update

                    # Check if we have timeframe info in optimized_data
                    tf = optimized_data.get("timeframe", "1m")
                    SENSOR_PARAMS[sensor_name] = {tf: {"tp_pct": params["tp_pct"], "sl_pct": params["sl_pct"]}}

            print(f"✅ Loaded optimized parameters for {len(optimized_data['sensors'])} sensors")
except Exception as e:
    print(f"⚠️ Failed to load optimized parameters: {e}")


# =====================================================
# 🔧 HELPER FUNCTIONS
# =====================================================


def get_sensor_params(sensor_id: str, timeframe: str = "1m") -> dict:
    """
    Get TP/SL parameters for a sensor at a specific timeframe.

    Supports both legacy format (single dict) and new multi-timeframe format.
    When exact TF not found, uses sensor's optimal (first configured) TF params.

    Args:
        sensor_id: Name of the sensor (e.g., "BollingerTouch")
        timeframe: Timeframe string (e.g., "1m", "5m", "15m", "1h")

    Returns:
        Dictionary with at least {"tp_pct": float, "sl_pct": float}
    """
    if sensor_id not in SENSOR_PARAMS:
        # Sensor not found, use default
        return SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.015, "sl_pct": 0.01})

    sensor_config = SENSOR_PARAMS[sensor_id]

    # Check if it's multi-timeframe format (has timeframe keys)
    if isinstance(sensor_config, dict):
        # Exact timeframe match
        if timeframe in sensor_config:
            return sensor_config[timeframe]

        # Check if it's legacy format (has tp_pct/sl_pct directly)
        if "tp_pct" in sensor_config:
            return sensor_config

        # Fallback: use sensor's optimal TF (first key that's a TF)
        tf_keys = [k for k in sensor_config.keys() if k in ("1m", "5m", "15m", "1h")]
        if tf_keys:
            optimal_tf = tf_keys[0]  # First configured TF is optimal
            return sensor_config[optimal_tf]

    # Final fallback to default
    return SENSOR_PARAMS["_default"].get(timeframe, {"tp_pct": 0.015, "sl_pct": 0.01})


def get_sensor_timeframe(sensor_id: str) -> str:
    """
    Get the primary timeframe for a sensor (legacy, backward compatible).

    Args:
        sensor_id: Name of the sensor

    Returns:
        Primary timeframe string (first in list if multiple)
    """
    tfs = get_sensor_timeframes(sensor_id)
    return tfs[0] if tfs else "1m"


def get_sensor_timeframes(sensor_id: str) -> list:
    """
    Get list of timeframes a sensor monitors.

    Args:
        sensor_id: Name of the sensor (e.g., "BollingerTouch")

    Returns:
        List of timeframe strings (e.g., ["5m", "15m"])
        Defaults to ["1m"] if sensor not found.

    Example:
        >>> get_sensor_timeframes("BollingerTouch")
        ["5m", "15m"]
    """
    tfs = SENSOR_TIMEFRAMES.get(sensor_id, "1m")
    # Ensure always returns list
    if isinstance(tfs, str):
        return [tfs]
    return list(tfs)
