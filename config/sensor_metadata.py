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
    # FOOTPRINT / ORDER FLOW (Dale/Dalton)
    # ==========================================
    "FootprintImbalance": {
        "function": "Momentum",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Aggressive buying/selling imbalance at specific price levels",
    },
    "FootprintAbsorption": {
        "function": "MeanReversion",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "High volume absorbed at extremes without price progression",
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
    "FootprintVolumeExhaustion": {
        "function": "MeanReversion",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Volume exhaustion at price extremes",
    },
    "FootprintDeltaPoCShift": {
        "function": "TrendFollowing",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Delta and POC shifting in the same direction (strong impulse)",
    },
    "CumulativeDelta": {
        "function": "Confirmation",
        "methodology": "VolumeBased",
        "data_required": ["ohlc", "volume"],
        "description": "Cumulative Delta tracking buyer/seller pressure over time",
    },
    # ==========================================
    # STRUCTURAL CONTEXT (Dalton Market Profile)
    # ==========================================
    "OneTimeframing": {
        "function": "Context",
        "methodology": "Structural",
        "data_required": ["ohlc"],
        "description": "Dalton One-Timeframing directional conviction filter",
    },
    "SessionValueArea": {
        "function": "Context",
        "methodology": "Structural",
        "data_required": ["ohlc", "volume"],
        "description": "Session-wide Value Area (VAH/VAL/POC) and Initial Balance context",
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
