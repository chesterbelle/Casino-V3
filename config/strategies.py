"""
====================================================
🎯 SENSOR TYPES & TRADING STRATEGIES — CASINO V3
====================================================

ARCHITECTURE:
- SENSOR_TYPES: Categorize sensors by WHAT they detect
- STRATEGIES: Define HOW to trade, using sensors from any type

A sensor belongs to ONE type but can be used in MULTIPLE strategies.
"""

from typing import Dict, List, Set

# =====================================================
# 📊 SENSOR TYPES (What the sensor detects)
# =====================================================

SENSOR_TYPES: Dict[str, List[str]] = {
    # -----------------------------------------------------
    # TREND INDICATORS - Direction of the market
    # -----------------------------------------------------
    "TrendIndicator": [
        "EMACrossover",
        "MACDCrossover",
        "Supertrend",
        "ADXFilter",
        "ParabolicSAR",
        "HigherTFTrend",
        "MTFImpulse",
    ],
    # -----------------------------------------------------
    # OSCILLATORS - Overbought/Oversold conditions
    # -----------------------------------------------------
    "Oscillator": [
        "RSIReversion",
        "StochasticReversion",
        "CCIReversion",
        "WilliamsRReversion",
        "AdaptiveRSI",
    ],
    # -----------------------------------------------------
    # VOLATILITY/BANDS - Price relative to bands
    # -----------------------------------------------------
    "VolatilityBands": [
        "BollingerTouch",
        "BollingerSqueeze",
        "BollingerRejection",
        "KeltnerReversion",
        "KeltnerBreakout",
        "ZScoreReversion",
    ],
    # -----------------------------------------------------
    # CANDLESTICK PATTERNS - Single/Multi candle formations
    # -----------------------------------------------------
    "CandlestickPattern": [
        "EngulfingPattern",
        "PinBarReversal",
        "RailsPattern",
        "MorningStar",
        "DojiIndecision",
        "TweezerPattern",
        "ThreeBar",
        "MarubozuMomentum",
        "WickRejection",
        "LongTail",
    ],
    # -----------------------------------------------------
    # STRUCTURAL PATTERNS - Multi-bar structures
    # -----------------------------------------------------
    "StructuralPattern": [
        "VCPPattern",
        "InsideBarBreakout",
        "DecelerationCandles",
        "ExtremeCandleRatio",
        "Fakeout",
    ],
    # -----------------------------------------------------
    # VOLUME ANALYSIS - Volume-based signals
    # -----------------------------------------------------
    "VolumeAnalysis": [
        "VolumeImbalance",
        "VolumeSpike",
        "VSAReversal",
        "AbsorptionBlock",
    ],
    # -----------------------------------------------------
    # SMART MONEY / ICT - Institutional concepts
    # -----------------------------------------------------
    "SmartMoneyConcepts": [
        "OrderBlock",
        "LiquidityVoid",
        "FVGRetest",
        "WyckoffSpring",
    ],
    # -----------------------------------------------------
    # VWAP BASED - Volume-weighted average price
    # -----------------------------------------------------
    "VWAPBased": [
        "VWAPDeviation",
        "VWAPBreakout",
        "VWAPMomentum",
    ],
    # -----------------------------------------------------
    # SUPPORT/RESISTANCE - Key price levels
    # -----------------------------------------------------
    "SupportResistance": [
        "EMA50Support",
        "SupportResistance",
    ],
    # -----------------------------------------------------
    # REGIME/FILTER - Market condition detection
    # -----------------------------------------------------
    "RegimeFilter": [
        "HurstRegime",
        "VolatilityWakeup",
        "MicroTrend",
        "SmartRange",
        "MomentumBurst",
        "OneTimeframing",
    ],
    # -----------------------------------------------------
    # ORDER FLOW - Footprint & Delta analysis
    # -----------------------------------------------------
    "OrderFlow": [
        "FootprintImbalance",
        "FootprintAbsorption",
        "FootprintPOCRejection",
        "FootprintDeltaDivergence",
        "FootprintStackedImbalance",
        "FootprintTrappedTraders",
        "FootprintVolumeExhaustion",
        "FootprintDeltaPoCShift",
    ],
}


# =====================================================
# 🎯 TRADING STRATEGIES (How to trade)
# =====================================================

STRATEGIES: Dict[str, dict] = {
    # -----------------------------------------------------
    # TREND RIDER - Seguir la dirección del mercado
    # -----------------------------------------------------
    "TrendRider": {
        "enabled": False,  # Disabled for demo - using QuickScalper
        "description": "Seguir la dirección del mercado con momentum",
        "logic": "Entrar en pullbacks dentro de tendencias establecidas",
        "sensors": [
            # Trend Indicators
            "EMACrossover",
            "MACDCrossover",
            "Supertrend",
            "ADXFilter",
            "ParabolicSAR",
            # Momentum
            "MomentumBurst",
            "MarubozuMomentum",
            # Multi-timeframe
            "HigherTFTrend",
            "MTFImpulse",
        ],
        "max_positions": 2,
    },
    # -----------------------------------------------------
    # MEAN REVERTER - Operar extremos esperando reversión
    # -----------------------------------------------------
    "MeanReverter": {
        "enabled": False,
        "description": "Operar extremos esperando reversión a la media",
        "logic": "Fade en zonas de sobrecompra/sobreventa",
        "sensors": [
            # Oscillators
            "RSIReversion",
            "StochasticReversion",
            "CCIReversion",
            "WilliamsRReversion",
            "AdaptiveRSI",
            # Bands
            "BollingerTouch",
            "KeltnerReversion",
            "ZScoreReversion",
            # Patterns at extremes
            "PinBarReversal",
            "DojiIndecision",
            # Context (macro trend)
            "HigherTFTrend",
        ],
        "max_positions": 3,
    },
    # -----------------------------------------------------
    # BREAKOUT HUNTER - Capturar movimientos explosivos
    # -----------------------------------------------------
    "BreakoutHunter": {
        "enabled": False,
        "description": "Capturar movimientos explosivos después de compresión",
        "logic": "Entrar cuando volatilidad se expande desde rango",
        "sensors": [
            # Structural
            "VCPPattern",
            "InsideBarBreakout",
            # Volatility expansion
            "BollingerSqueeze",
            "KeltnerBreakout",
            "VolatilityWakeup",
            # Volume confirmation
            "VolumeImbalance",
            # VWAP
            "VWAPBreakout",
            # Context (macro trend)
            "HigherTFTrend",
        ],
        "max_positions": 1,
    },
    # -----------------------------------------------------
    # QUICK SCALPER - Scalping de alta frecuencia optimizado
    # -----------------------------------------------------
    "QuickScalper": {
        "enabled": False,  # DISABLED IN PHASE 600
        "description": "Scalping de alta frecuencia con TP/SL ajustados",
        "logic": "Señales rápidas con confirmación de volumen. 1m-5m execution.",
        "sensors": [
            # === PRIMARY TRIGGERS (Alta frecuencia, alto score) ===
            "VolumeSpike",  # ⭐ BEST: WR 70%, Exp 0.20, Score 0.946
            "VWAPMomentum",  # WR 92%, 38K+ trades
            "LongTail",  # WR 32%, Exp 0.10, SL ajustado 1.1%
            # === FOOTPRINT (Ultra-tight stops 0.5%-0.8%) ===
            "FootprintVolumeExhaustion",
            "FootprintPOCRejection",
            "FootprintTrappedTraders",
            "FootprintImbalance",
            "FootprintAbsorption",
            "FootprintDeltaDivergence",
            "FootprintStackedImbalance",
            "FootprintDeltaPoCShift",
            # === FAST PATTERNS (1m-5m) ===
            "EngulfingPattern",  # 1m TF, SL 1.1%
            "SmartRange",  # 1m TF, TP/SL 3.1%/2.5%
            "WickRejection",  # 5m TF, detecta rechazo rápido
            "MicroTrend",  # 1m-5m TF
            # === VOLUME CONFIRMATION ===
            "AbsorptionBlock",  # SL 5.6% - detecta acumulación
            # === CONTEXT (Filtro macro) ===
            "HigherTFTrend",  # Filtro de tendencia HTF
        ],
        "max_positions": 1,
    },
    # -----------------------------------------------------
    # FOOTPRINT SCALPER - Order Flow (Synthetic)
    # -----------------------------------------------------
    "FootprintScalper": {
        "enabled": True,  # ENABLED IN PHASE 600
        "description": "Scalping based on synthetic Order Flow Imbalance and Market Profile",
        "logic": "Follow aggressive imbalances, fade absorption. Context via Aggregator Consensus.",
        "sensors": [
            # --- Primary Triggers (Order Flow) ---
            "FootprintAbsorption",
            "FootprintDeltaDivergence",
            "FootprintVolumeExhaustion",
            "FootprintPOCRejection",
            "FootprintTrappedTraders",
            "FootprintImbalance",
            "FootprintStackedImbalance",
            "FootprintDeltaPoCShift",
            "CumulativeDelta",
            "OneTimeframing",
            # --- High Performance Confirmations ---
            "VolumeSpike",  # WR 64%, PF 1.80 (Strongest confirmation)
            "RangeExpansion",  # WR 45%, PF 0.88 (Better than Squeeze)
            # NOTE: Other context sensors (CCI, Bollinger, Trend) are NOT listed here.
            # They will still vote in the Aggregator (contributing to Consensus Score),
            # but they cannot trigger a trade on their own. This ensures we only
            # trade when Order Flow or Volume confirms.
        ],
        "max_positions": 1,
    },
    # -----------------------------------------------------
    # SMART MONEY FOLLOWER - Seguir flujo institucional
    # -----------------------------------------------------
    "SmartMoneyFollower": {
        "enabled": False,  # BEST in backtest: -0.59% (30d LTC)
        "description": "Seguir huellas institucionales y manipulación",
        "logic": "Detectar acumulación/distribución y actuar con smart money",
        "sensors": [
            # ICT Concepts
            "OrderBlock",
            "LiquidityVoid",
            "FVGRetest",
            "WyckoffSpring",
            # Volume
            "AbsorptionBlock",
            "VSAReversal",
            "VolumeSpike",
            # VWAP
            "VWAPMomentum",
            "VWAPDeviation",
            # Context (macro trend)
            "HigherTFTrend",
        ],
        "max_positions": 2,
    },
    # -----------------------------------------------------
    # PATTERN TRADER - Operar patrones de velas
    # -----------------------------------------------------
    "PatternTrader": {
        "enabled": False,
        "description": "Operar patrones clásicos de velas",
        "logic": "Identificar reversiones con patrones de alta probabilidad",
        "sensors": [
            # Candlestick patterns
            "EngulfingPattern",
            "PinBarReversal",
            "RailsPattern",
            "MorningStar",
            "TweezerPattern",
            "ThreeBar",
            "WickRejection",
            "LongTail",
            # Context
            "EMA50Support",
            "SupportResistance",
            # Context (macro trend)
            "HigherTFTrend",
        ],
        "max_positions": 2,
    },
    # -----------------------------------------------------
    # ALPHA EDGE - Top performers by expectancy (data-driven)
    # -----------------------------------------------------
    "AlphaEdge": {
        "enabled": False,  # Backtest: +0.04% (3rd place)
        "description": "Los 15 mejores sensores por expectancy optimizada",
        "logic": "Selección basada en datos: solo sensores con Exp > 0.5%",
        "sensors": [
            # === TOP TIER (Exp > 1.0%) ===
            "MorningStar",  # Exp: 1.730% ⭐ BEST - Candlestick pattern 3-bar
            "BollingerSqueeze",  # Exp: 1.515% - Volatility compression breakout
            "MomentumBurst",  # Exp: 1.213% - Momentum explosion
            # === HIGH TIER (Exp 0.6% - 1.0%) ===
            "WyckoffSpring",  # Exp: 0.839% - SMC spring pattern
            "KeltnerBreakout",  # Exp: 0.820% - Keltner channel breakout
            "VolumeSpike",  # Exp: 0.818% - Volume confirmation
            "VolatilityWakeup",  # Exp: 0.761% - Volatility regime change
            "Supertrend",  # Exp: 0.680% - Trend following
            "RailsPattern",  # Exp: 0.663% - Candlestick reversal
            "VolumeImbalance",  # Exp: 0.652% - Volume imbalance
            "ThreeBar",  # Exp: 0.629% - Three bar pattern
            "BollingerRejection",  # Exp: 0.603% - BB rejection
            # === SOLID TIER (Exp 0.5% - 0.6%) ===
            "EMACrossover",  # Exp: 0.572% - Trend entry
            "BollingerTouch",  # Exp: 0.508% - Mean reversion at bands
            # === CONTEXT (Essential for HTF alignment) ===
            "HigherTFTrend",  # Exp: 0.535% - HTF direction filter
        ],
        "max_positions": 2,
    },
    # -----------------------------------------------------
    # SYNERGY FLOW - Complementary sensors (knowledge-based)
    # -----------------------------------------------------
    "SynergyFlow": {
        "enabled": False,
        "description": "Sensores complementarios con jerarquía de confirmación",
        "logic": "Context → Trigger → Pattern → Volume (cada señal requiere múltiples perspectivas)",
        "sensors": [
            # === LAYER 1: CONTEXT (Macro Direction + Regime) ===
            # Estos sensores definen SI debemos operar y en qué dirección
            "HigherTFTrend",  # Dirección HTF (1h/4h) - No operar contra tendencia macro
            "HurstRegime",  # Régimen de mercado: trending vs ranging
            "ADXFilter",  # Fuerza de tendencia (solo operar si ADX > umbral)
            # === LAYER 2: TREND TRIGGERS (Primary Entry Signals) ===
            # Señales de entrada principales que siguen la tendencia
            "Supertrend",  # Flip de supertrend = entrada de tendencia
            "EMACrossover",  # Cruce EMA rápida/lenta
            "MACDCrossover",  # Confirmación momentum MACD
            # === LAYER 3: PATTERN PRECISION (High-Probability Entries) ===
            # Patrones de precisión para entradas óptimas
            "MorningStar",  # Patrón de reversión 3-bar (mejor Exp)
            "RailsPattern",  # Dos velas opuestas = reversión
            "PinBarReversal",  # Pinbar en niveles clave
            "InsideBarBreakout",  # Rompimiento de inside bar (compresión)
            # === LAYER 4: VOLATILITY & STRUCTURE ===
            # Identificar expansión de volatilidad y estructuras
            "BollingerSqueeze",  # Squeeze = próxima expansión (breakout)
            "KeltnerBreakout",  # Rompimiento de Keltner = momentum
            "VCPPattern",  # Volatility Contraction Pattern
            # === LAYER 5: VOLUME CONFIRMATION ===
            # Volumen valida la señal (smart money)
            "VolumeSpike",  # Spike de volumen = interés institucional
            "VolumeImbalance",  # Imbalance = presión direccional
            "AbsorptionBlock",  # Absorción = acumulación/distribución
            # === LAYER 6: KEY LEVELS (S/R Context) ===
            # Entrar solo en niveles significativos
            "EMA50Support",  # EMA50 como soporte/resistencia dinámico
            "SupportResistance",  # Niveles S/R horizontales
        ],
        "max_positions": 2,
    },
    # -----------------------------------------------------
    # DEBUG ALL - Todos los sensores (solo para debugging)
    # -----------------------------------------------------
    "DebugAll": {
        "enabled": False,  # Enabled for training/debugging
        "description": "Todos los sensores activos para debugging",
        "logic": "Máxima cantidad de señales para probar el sistema",
        "sensors": [
            # Trend
            "ADXFilter",
            "EMACrossover",
            "MACDCrossover",
            "Supertrend",
            "ParabolicSAR",
            "HigherTFTrend",
            "MTFImpulse",
            "EMA50Support",
            # Oscillators
            "RSIReversion",
            "StochasticReversion",
            "CCIReversion",
            "WilliamsRReversion",
            "AdaptiveRSI",
            # Bands
            "BollingerTouch",
            "BollingerSqueeze",
            "BollingerRejection",
            "KeltnerReversion",
            "KeltnerBreakout",
            "ZScoreReversion",
            # Patterns
            "EngulfingPattern",
            "PinBarReversal",
            "RailsPattern",
            "MorningStar",
            "DojiIndecision",
            "TweezerPattern",
            "ThreeBar",
            "MarubozuMomentum",
            "WickRejection",
            "LongTail",
            # Structural
            "VCPPattern",
            "InsideBarBreakout",
            "DecelerationCandles",
            "ExtremeCandleRatio",
            "Fakeout",
            # Volume
            "VolumeImbalance",
            "VolumeSpike",
            "VSAReversal",
            "AbsorptionBlock",
            # SMC
            "OrderBlock",
            "LiquidityVoid",
            "FVGRetest",
            "WyckoffSpring",
            # Momentum
            "MomentumBurst",
            "MicroTrend",
            "SmartRange",
            # VWAP
            "VWAPDeviation",
            "VWAPBreakout",
            "VWAPMomentum",
            # Regime
            "HurstRegime",
            "VolatilityWakeup",
            "SupportResistance",
            # Footprint
            "FootprintImbalance",
            "FootprintAbsorption",
            "FootprintPOCRejection",
            "FootprintDeltaDivergence",
            "FootprintStackedImbalance",
            "FootprintTrappedTraders",
            "FootprintDeltaPoCShift",
            "CumulativeDelta",
        ],
        "max_positions": 3,
    },
}


# =====================================================
# 🔧 HELPER FUNCTIONS
# =====================================================


def get_sensor_type(sensor_name: str) -> str:
    """Get the type category for a sensor."""
    for type_name, sensors in SENSOR_TYPES.items():
        if sensor_name in sensors:
            return type_name
    return "Unknown"


def get_sensors_by_type(type_name: str) -> List[str]:
    """Get all sensors of a specific type."""
    return SENSOR_TYPES.get(type_name, [])


def get_active_sensors() -> Set[str]:
    """Get sensors from all enabled strategies."""
    active = set()
    for config in STRATEGIES.values():
        if config.get("enabled", False):
            active.update(config.get("sensors", []))
    return active


def get_enabled_strategies() -> List[str]:
    """Get list of enabled strategy names."""
    return [name for name, config in STRATEGIES.items() if config.get("enabled", False)]


def get_strategy_for_sensor(sensor_name: str) -> List[str]:
    """Find which strategies use a sensor (can be multiple)."""
    strategies = []
    for name, config in STRATEGIES.items():
        if sensor_name in config.get("sensors", []):
            strategies.append(name)
    return strategies


def get_strategy_config(strategy_name: str) -> dict:
    """Get configuration for a specific strategy."""
    return STRATEGIES.get(strategy_name, {})


def enable_only(strategy_name: str):
    """Enable only the specified strategy, disable others."""
    for name, config in STRATEGIES.items():
        config["enabled"] = name == strategy_name


def enable_strategies(strategy_names: List[str]):
    """Enable multiple strategies."""
    for name, config in STRATEGIES.items():
        config["enabled"] = name in strategy_names
