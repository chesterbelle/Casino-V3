"""
Coin Profiles — v8.4 Crystal Reforge

Comprehensive profiles defining ALL Crystal Layer parameters per coin type.
Each profile contains parameters for sensors, scenarios, quality scorer, targets, and guardians.

Profile Names:
- VOLATIL_BAJO_FLOW: Thin books, low trade density (SUI, AVAX, LTC)
- EFICIENTE_MEGACAP: Deep books, tight spreads, high flow (BTC, ETH)
- BALANCED_MID: Moderate characteristics (SOL, ADA, BNB, LINK, DOGE)

Classification Metrics (measured from L2 data):
- spread_ratio: current_spread / avg_5m_spread (1.0 = normal, >1.0 = wide)
- depth_ratio: L2 bid_vol / ask_vol within 0.2% of mid (higher = deeper book)
- speed: trades per second (higher = more active market)
"""

COIN_PROFILES = {
    # =========================================================================
    # VOLATIL_BAJO_FLOW — Thin books, low trade density
    # Coins: SUI, AVAX, LTC
    # Characteristics: spread_ratio < 2.0, depth_ratio < 1.5, speed < 0.04
    # =========================================================================
    "VOLATIL_BAJO_FLOW": {
        "description": "Libros delgados, bajo flujo — edge de reversion fuerte",
        "characteristics": {
            "spread_ratio": {"min": 0.0, "max": 2.0},
            "depth_ratio": {"min": 0.0, "max": 1.5},
            "speed": {"min": 0.0, "max": 0.04},
        },
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.5,
                "concentration_min": 0.40,
                "noise_max": 0.40,
                "stagnation_floor_pct": 0.08,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0002,
                "max_break_age": 90.0,
                "cvd_divergence_threshold": 0.25,
            },
            "liquidity_exhaustion": {
                "min_tests": 3,
                "declining_threshold": 0.75,
                "min_bounce_pct": 0.0003,
                "test_memory_seconds": 120.0,
            },
            "trend_acceptance": {
                "min_candles_outside": 3,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.001,
                "max_pullback_penetration_pct": 0.001,
            },
        },
        "scenarios": {
            "enabled": ["TacticalAbsorptionV2", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {
                "exhaustion": 0.4,
                "regime": 0.3,
                "structure": 0.15,
                "liquidity": 0.1,
                "spread": 0.05,
            },
            "grade_thresholds": {"A": 0.7, "B": 0.4},
        },
        "targets": {
            "TacticalAbsorptionV2": {"tp_pct": 0.009, "sl_pct": 0.015},  # 0.90% fallback, SL=1.50% (POC-optimized)
            "failed_breakout": {"tp_pct": 0.01, "sl_pct": 0.01},  # 1.00% (auditor optimal)
            "liquidity_exhaustion": {"tp_pct": 0.006, "sl_pct": 0.006},
            "trend_acceptance": {"tp_pct": 0.009, "sl_pct": 0.009},
        },
        "guardians": {
            "l2_ratio_min": 0.5,  # Thin Wall para BALANCE/UP (mejor MFE/MAE)
            "l2_ratio_min_trend_down": 2.0,  # High Wall para BEAR (High Wall tiene mejor MFE/MAE en DOWN)
            "spread_max_ratio": 2.0,
        },
    },
    "EFICIENTE_MEGACAP": {
        "description": "Ultra-eficientes — libros profundos, spreads tight",
        "characteristics": {
            "spread_ratio": {"min": 0.0, "max": 1.5},  # Spread muy tight
            "depth_ratio": {"min": 1.5, "max": 100.0},  # Libro profundo
            "speed": {"min": 0.07, "max": 100.0},  # Alta densidad
        },
        # --- SENSOR PARAMETERS ---
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.5,  # Más estricto
                "concentration_min": 0.60,  # Más estricto
                "noise_max": 0.25,  # Más estricto
                "stagnation_floor_pct": 0.12,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0005,  # 0.05%
                "max_break_age": 45.0,  # 45 segundos
                "cvd_divergence_threshold": 0.35,
            },
            "liquidity_exhaustion": {
                "min_tests": 4,
                "declining_threshold": 0.70,
                "min_bounce_pct": 0.0005,
                "test_memory_seconds": 90.0,
            },
            "trend_acceptance": {
                "min_candles_outside": 4,
                "cvd_confirmation_threshold": 6.0,
                "pullback_tolerance_pct": 0.0008,
                "max_pullback_penetration_pct": 0.0008,
            },
        },
        # --- SCENARIO PARAMETERS ---
        "scenarios": {
            "enabled": ["TacticalAbsorptionV2"],  # Solo el principal
        },
        # --- QUALITY SCORER PARAMETERS ---
        "quality_scorer": {
            "weights": {
                "exhaustion": 0.40,
                "regime": 0.30,
                "structure": 0.15,
                "liquidity": 0.10,
                "spread": 0.05,
            },
            "grade_thresholds": {"A": 0.80, "B": 0.50},
        },
        # --- TARGET PARAMETERS ---
        "targets": {
            "TacticalAbsorptionV2": {"tp_pct": 0.005, "sl_pct": 0.005},  # 0.50%
            "failed_breakout": {"tp_pct": 0.006, "sl_pct": 0.006},  # 0.60%
            "liquidity_exhaustion": {"tp_pct": 0.004, "sl_pct": 0.004},  # 0.40%
            "trend_acceptance": {"tp_pct": 0.006, "sl_pct": 0.006},  # 0.60%
        },
        # --- GUARDIAN PARAMETERS ---
        "guardians": {
            "l2_ratio_min": 2.5,
            "spread_max_ratio": 1.5,
        },
    },
    # =========================================================================
    # BALANCED_MID — Moderate characteristics
    # Coins: SOL, ADA, BNB, LINK, DOGE
    # Characteristics: spread_ratio < 2.5, depth_ratio 1.0-3.0, speed 0.04-0.07
    # =========================================================================
    "BALANCED_MID": {
        "description": "Balanceados — parámetros intermedios",
        "characteristics": {
            "spread_ratio": {"min": 0.0, "max": 2.5},  # Spread moderado
            "depth_ratio": {"min": 1.0, "max": 3.0},  # Profundidad media
            "speed": {"min": 0.04, "max": 0.07},  # Densidad media
        },
        # --- SENSOR PARAMETERS ---
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.0,  # Default
                "concentration_min": 0.50,  # Default
                "noise_max": 0.30,  # Intermedio
                "stagnation_floor_pct": 0.10,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0003,  # 0.03%
                "max_break_age": 60.0,  # 60 segundos
                "cvd_divergence_threshold": 0.30,
            },
            "liquidity_exhaustion": {
                "min_tests": 3,
                "declining_threshold": 0.70,
                "min_bounce_pct": 0.0004,
                "test_memory_seconds": 100.0,
            },
            "trend_acceptance": {
                "min_candles_outside": 3,
                "cvd_confirmation_threshold": 5.0,
                "pullback_tolerance_pct": 0.001,
                "max_pullback_penetration_pct": 0.001,
            },
        },
        # --- SCENARIO PARAMETERS ---
        "scenarios": {
            "enabled": ["TacticalAbsorptionV2", "failed_breakout"],
        },
        # --- QUALITY SCORER PARAMETERS ---
        "quality_scorer": {
            "weights": {
                "exhaustion": 0.30,
                "regime": 0.25,
                "structure": 0.20,
                "liquidity": 0.15,
                "spread": 0.10,
            },
            "grade_thresholds": {"A": 0.70, "B": 0.40},
        },
        # --- TARGET PARAMETERS ---
        "targets": {
            "TacticalAbsorptionV2": {"tp_pct": 0.008, "sl_pct": 0.008},  # 0.80%
            "failed_breakout": {"tp_pct": 0.009, "sl_pct": 0.009},  # 0.90%
            "liquidity_exhaustion": {"tp_pct": 0.005, "sl_pct": 0.005},  # 0.50%
            "trend_acceptance": {"tp_pct": 0.009, "sl_pct": 0.009},  # 0.90%
        },
        # --- GUARDIAN PARAMETERS ---
        "guardians": {
            "l2_ratio_min": 2.0,
            "spread_max_ratio": 2.0,
        },
    },
}

# Default profile for unknown coins
DEFAULT_PROFILE = "BALANCED_MID"
