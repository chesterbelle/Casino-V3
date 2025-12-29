"""
================================================
🏷️ SENSOR METADATA — DUAL CATEGORIZATION
================================================

Each sensor is classified by:
1. FUNCTION: What it detects (TrendFollowing, MeanReversion, Breakout, etc.)
2. METHODOLOGY: How it processes data (PriceAction, IndicatorDerived, etc.)

This enables analytics like:
- "Which methodology is performing best?"
- "Create more sensors of type X"
- "Penalize correlation between same-methodology sensors"
"""

from typing import Dict, List, Literal, TypedDict

# ==============================================
# 📊 TYPE DEFINITIONS
# ==============================================


class SensorMeta(TypedDict):
    """Metadata for a single sensor."""

    function: Literal[
        "TrendFollowing",  # Follow established trends
        "MeanReversion",  # Fade extremes, expect reversion
        "Breakout",  # Catch explosive moves after compression
        "Momentum",  # Catch acceleration/deceleration
        "Confirmation",  # Confirm other signals (not standalone)
        "Context",  # HTF/Regime detection (filters, not signals)
    ]
    methodology: Literal[
        "PriceAction",  # Pure OHLC, no indicators (Doji, PinBar, etc.)
        "IndicatorDerived",  # Uses calculated indicators (RSI, MACD, EMA)
        "VolumeBased",  # Requires volume data
        "Statistical",  # Uses statistical analysis (σ, Hurst, ZScore)
        "Structural",  # Multi-bar price patterns (VCP, InsideBar)
        "Hybrid",  # Combines multiple methodologies
    ]
    data_required: List[Literal["ohlc", "volume", "indicator"]]
    description: str


# ==============================================
# 🏷️ SENSOR METADATA REGISTRY
# ==============================================

SENSOR_METADATA: Dict[str, SensorMeta] = {
    # ==========================================
    # PRICE ACTION (Pure OHLC, no indicators)
    # ==========================================
    "DojiIndecision": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Detects doji candles indicating indecision/reversal",
    },
    "PinBarReversal": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Long wick rejection candles at extremes",
    },
    "EngulfingPattern": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Bullish/bearish engulfing reversal pattern",
    },
    "RailsPattern": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Two opposite candles of similar size (railroad tracks)",
    },
    "MorningStar": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Three-candle reversal pattern at bottoms",
    },
    "TweezerPattern": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Two candles with matching highs/lows",
    },
    "ThreeBar": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Three-bar reversal pattern",
    },
    "MarubozuMomentum": {
        "function": "Momentum",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Full-body candle indicating strong momentum",
    },
    "WickRejection": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Price rejected via long wick",
    },
    "LongTail": {
        "function": "MeanReversion",
        "methodology": "PriceAction",
        "data_required": ["ohlc"],
        "description": "Long lower/upper shadow indicating rejection",
    },
    # ==========================================
    # STRUCTURAL (Multi-bar price patterns)
    # ==========================================
    "VCPPattern": {
        "function": "Breakout",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Volatility Contraction Pattern before breakout",
    },
    "InsideBarBreakout": {
        "function": "Breakout",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Inside bar followed by breakout",
    },
    "DecelerationCandles": {
        "function": "MeanReversion",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Decreasing candle sizes indicating exhaustion",
    },
    "ExtremeCandleRatio": {
        "function": "MeanReversion",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Extreme body/wick ratio indicating reversal",
    },
    "Fakeout": {
        "function": "MeanReversion",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Failed breakout followed by reversal",
    },
    # ==========================================
    # INDICATOR-DERIVED (Calculated indicators)
    # ==========================================
    "EMACrossover": {
        "function": "TrendFollowing",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "EMA fast/slow crossover",
    },
    "MACDCrossover": {
        "function": "TrendFollowing",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "MACD line crossing signal line",
    },
    "Supertrend": {
        "function": "TrendFollowing",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Supertrend indicator direction change",
    },
    "ADXFilter": {
        "function": "Context",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "ADX strength filter for trend confirmation",
    },
    "ParabolicSAR": {
        "function": "TrendFollowing",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Parabolic SAR flip",
    },
    "RSIReversion": {
        "function": "MeanReversion",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "RSI at overbought/oversold levels",
    },
    "StochasticReversion": {
        "function": "MeanReversion",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Stochastic at extreme levels",
    },
    "CCIReversion": {
        "function": "MeanReversion",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "CCI at extreme levels",
    },
    "WilliamsRReversion": {
        "function": "MeanReversion",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Williams %R at extreme levels",
    },
    "AdaptiveRSI": {
        "function": "MeanReversion",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "RSI with dynamic thresholds",
    },
    "EMA50Support": {
        "function": "Confirmation",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Price bouncing off EMA50",
    },
    # ==========================================
    # STATISTICAL (σ, Hurst, regression)
    # ==========================================
    "BollingerTouch": {
        "function": "MeanReversion",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Price touching Bollinger Bands",
    },
    "BollingerSqueeze": {
        "function": "Breakout",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Bollinger band compression before breakout",
    },
    "BollingerRejection": {
        "function": "MeanReversion",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Price rejected at Bollinger Bands",
    },
    "KeltnerReversion": {
        "function": "MeanReversion",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Price at Keltner channel extremes",
    },
    "KeltnerBreakout": {
        "function": "Breakout",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Price breaking Keltner channels",
    },
    "ZScoreReversion": {
        "function": "MeanReversion",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Price at extreme Z-score levels",
    },
    "HurstRegime": {
        "function": "Context",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Hurst exponent regime detection (trending/ranging)",
    },
    "VolatilityWakeup": {
        "function": "Breakout",
        "methodology": "Statistical",
        "data_required": ["ohlc", "indicator"],
        "description": "Volatility expanding from low levels",
    },
    # ==========================================
    # VOLUME-BASED (Requires volume data)
    # ==========================================
    "VolumeSpike": {
        "function": "Confirmation",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Unusual volume spike",
    },
    "VolumeImbalance": {
        "function": "Confirmation",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Buy/sell volume imbalance",
    },
    "VSAReversal": {
        "function": "MeanReversion",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Volume Spread Analysis reversal signals",
    },
    "AbsorptionBlock": {
        "function": "Confirmation",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Large volume absorbed at price level",
    },
    # ==========================================
    # HYBRID (Multiple methodologies)
    # ==========================================
    "VWAPDeviation": {
        "function": "MeanReversion",
        "methodology": "Hybrid",
        "data_required": ["ohlc", "volume", "indicator"],
        "description": "Price deviation from VWAP (volume + price)",
    },
    "VWAPBreakout": {
        "function": "Breakout",
        "methodology": "Hybrid",
        "data_required": ["ohlc", "volume", "indicator"],
        "description": "Price breaking through VWAP",
    },
    "VWAPMomentum": {
        "function": "TrendFollowing",
        "methodology": "Hybrid",
        "data_required": ["ohlc", "volume", "indicator"],
        "description": "Price momentum relative to VWAP",
    },
    "OrderBlock": {
        "function": "Confirmation",
        "methodology": "Hybrid",
        "data_required": ["ohlc", "volume"],
        "description": "ICT order block detection (price + volume structure)",
    },
    "LiquidityVoid": {
        "function": "Breakout",
        "methodology": "Hybrid",
        "data_required": ["ohlc", "volume"],
        "description": "Fair value gaps / liquidity voids",
    },
    "FVGRetest": {
        "function": "MeanReversion",
        "methodology": "Hybrid",
        "data_required": ["ohlc"],
        "description": "Fair Value Gap retest",
    },
    "WyckoffSpring": {
        "function": "MeanReversion",
        "methodology": "Hybrid",
        "data_required": ["ohlc", "volume"],
        "description": "Wyckoff spring/upthrust pattern",
    },
    # ==========================================
    # CONTEXT SENSORS (HTF / Regime filters)
    # ==========================================
    "HigherTFTrend": {
        "function": "Context",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Higher timeframe trend direction",
    },
    "MTFImpulse": {
        "function": "Context",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Multi-timeframe impulse alignment",
    },
    "SupportResistance": {
        "function": "Context",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Key support/resistance levels",
    },
    "MicroTrend": {
        "function": "Context",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Short-term trend detection",
    },
    "SmartRange": {
        "function": "Context",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Range-bound market detection",
    },
    "MomentumBurst": {
        "function": "Momentum",
        "methodology": "IndicatorDerived",
        "data_required": ["ohlc", "indicator"],
        "description": "Sudden momentum acceleration",
    },
    # ==========================================
    # NEW STRUCTURAL SENSORS (2024-12)
    # ==========================================
    "NarrowRange7": {
        "function": "Breakout",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Smallest range of last 7 bars - volatility compression",
    },
    "ConsecutiveCandles": {
        "function": "MeanReversion",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "N consecutive same-direction candles - exhaustion signal",
    },
    "RangeExpansion": {
        "function": "Momentum",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Current range > 2x average - momentum breakout",
    },
    "ThreeWhiteSoldiers": {
        "function": "TrendFollowing",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Three consecutive bullish candles with higher closes",
    },
    "ThreeBlackCrows": {
        "function": "TrendFollowing",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Three consecutive bearish candles with lower closes",
    },
    "WideRangeBar": {
        "function": "Momentum",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Unusually wide range bar indicating strong momentum",
    },
    "DoubleBottom": {
        "function": "MeanReversion",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "W-pattern with two similar lows - bullish reversal",
    },
    "DoubleTop": {
        "function": "MeanReversion",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "M-pattern with two similar highs - bearish reversal",
    },
    "HigherHighsLowerLows": {
        "function": "TrendFollowing",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Swing structure HH/HL or LH/LL trend detection",
    },
    "IslandReversal": {
        "function": "MeanReversion",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Price isolated by gaps on both sides - strong reversal",
    },
    # ==========================================
    # FOOTPRINT / ORDER FLOW (Synthetic)
    # ==========================================
    "FootprintImbalance": {
        "function": "Momentum",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],  # Synthetic uses OHLCV
        "description": "Aggressive buying/selling imbalance (Synthetic)",
    },
    "FootprintAbsorption": {
        "function": "MeanReversion",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],  # Synthetic uses OHLCV
        "description": "High volume at extremes without price progression (Synthetic)",
    },
    "FootprintPOCRejection": {
        "function": "MeanReversion",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Price rejection at previous Point of Control",
    },
    "FootprintDeltaDivergence": {
        "function": "MeanReversion",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Divergence between Price Trend and Delta Trend",
    },
    "FootprintStackedImbalance": {
        "function": "Momentum",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Consecutive price levels with aggressive imbalance",
    },
    "FootprintTrappedTraders": {
        "function": "MeanReversion",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "High volume at wicks followed by reversal",
    },
}


# ==============================================
# 🔧 HELPER FUNCTIONS
# ==============================================


def get_sensor_metadata(sensor_name: str) -> SensorMeta | None:
    """Get metadata for a specific sensor."""
    return SENSOR_METADATA.get(sensor_name)


def get_sensors_by_function(function: str) -> List[str]:
    """Get all sensors of a specific function type."""
    return [name for name, meta in SENSOR_METADATA.items() if meta["function"] == function]


def get_sensors_by_methodology(methodology: str) -> List[str]:
    """Get all sensors using a specific methodology."""
    return [name for name, meta in SENSOR_METADATA.items() if meta["methodology"] == methodology]


def get_methodology_distribution() -> Dict[str, int]:
    """Get count of sensors per methodology."""
    distribution: Dict[str, int] = {}
    for meta in SENSOR_METADATA.values():
        method = meta["methodology"]
        distribution[method] = distribution.get(method, 0) + 1
    return distribution


def get_function_distribution() -> Dict[str, int]:
    """Get count of sensors per function."""
    distribution: Dict[str, int] = {}
    for meta in SENSOR_METADATA.values():
        func = meta["function"]
        distribution[func] = distribution.get(func, 0) + 1
    return distribution


# ==============================================
# 📊 SUMMARY (for quick reference)
# ==============================================
# Run this file directly to see the distribution

if __name__ == "__main__":
    print("\n📊 SENSOR METHODOLOGY DISTRIBUTION")
    print("=" * 40)
    for method, count in sorted(get_methodology_distribution().items(), key=lambda x: -x[1]):
        sensors = get_sensors_by_methodology(method)
        print(f"  {method}: {count}")
        for s in sensors[:3]:
            print(f"    - {s}")
        if len(sensors) > 3:
            print(f"    ... and {len(sensors) - 3} more")

    print("\n🎯 SENSOR FUNCTION DISTRIBUTION")
    print("=" * 40)
    for func, count in sorted(get_function_distribution().items(), key=lambda x: -x[1]):
        print(f"  {func}: {count}")

    print(f"\n✅ Total sensors cataloged: {len(SENSOR_METADATA)}")
