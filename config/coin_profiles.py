"""
Coin Profiles — Parameter Configuration (Per-Cluster)
=====================================================

Parameters are organized by cluster (profile name). Classification
is handled by config/clusters.json (centroid-based).

Each profile contains:
  - sensors: absorption_detector, failed_breakout, liquidity_exhaustion, trend_acceptance
  - scenarios: enabled scenario list
  - quality_scorer: weights and grade thresholds
  - targets: per-scenario TP/SL (with optional per-regime overrides)
  - guardians: L2 ratio, spread thresholds

Membership is defined in clusters.json, not here.
"""

COIN_PROFILES = {
    # =========================================================================
    # MEGA_LIQUID — BTC, ETH
    # Ultra-deep books, tight spreads, institutional flow
    # Targets tight (market moves slow), quality strict
    # =========================================================================
    "MEGA_LIQUID": {
        "description": "Mega-cap institucional — BTC, ETH",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.0,
                "concentration_min": 0.60,
                "noise_max": 0.25,
                "stagnation_floor_pct": 0.12,
                "cooldown": 300.0,
                "volatility_z_max": 2.0,
                "displacement_z_max": 2.0,
                "absorption_score_min": 0.5,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0005,
                "max_break_age": 45.0,
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
        "scenarios": {
            "enabled": ["tactical_absorption", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.40, "regime": 0.30, "structure": 0.15, "liquidity": 0.10, "spread": 0.05},
            "grade_thresholds": {"A": 0.80, "B": 0.50},
        },
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.040},
            "failed_breakout": {"tp_pct": 0.010, "sl_pct": 0.010},
            "liquidity_exhaustion": {"tp_pct": 0.010, "sl_pct": 0.010},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.040},
        },
        "guardians": {
            "l2_ratio_min": 2.5,
            "spread_max_ratio": 1.5,
        },
    },
    # =========================================================================
    # MAJOR_LIQUID — SOL, BNB, XRP, DOGE, SUI
    # Large-cap, high liquidity, vol moderada
    # Balanced parameters
    # =========================================================================
    "MAJOR_LIQUID": {
        "description": "Large-cap alta liquidez — SOL, BNB, XRP, DOGE, SUI",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 1.8,
                "concentration_min": 0.55,
                "noise_max": 0.30,
                "stagnation_floor_pct": 0.10,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0006,
                "max_break_age": 60.0,
                "cvd_divergence_threshold": 0.30,
            },
            "liquidity_exhaustion": {
                "min_tests": 3,
                "declining_threshold": 0.72,
                "min_bounce_pct": 0.0007,
                "test_memory_seconds": 100.0,
            },
            "trend_acceptance": {
                "min_candles_outside": 3,
                "cvd_confirmation_threshold": 5.0,
                "pullback_tolerance_pct": 0.001,
                "max_pullback_penetration_pct": 0.001,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.35, "regime": 0.28, "structure": 0.17, "liquidity": 0.12, "spread": 0.08},
            "grade_thresholds": {"A": 0.70, "B": 0.45},
        },
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.040},
            "failed_breakout": {"tp_pct": 0.010, "sl_pct": 0.010},
            "liquidity_exhaustion": {"tp_pct": 0.010, "sl_pct": 0.010},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.040},
        },
        "guardians": {
            "l2_ratio_min": 1.5,
            "l2_ratio_min_trend_down": 2.0,
            "spread_max_ratio": 1.8,
        },
    },
    # =========================================================================
    # MID_LIQUID — AVAX, ADA, LINK
    # Mid-cap, parameters validated in LTC datasets (iter 3)
    # Slightly more aggressive targets
    # =========================================================================
    "MID_LIQUID": {
        "description": "Mid-cap, edge validado — AVAX, ADA, LINK",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.0,
                "concentration_min": 0.50,
                "noise_max": 0.40,
                "stagnation_floor_pct": 0.08,
                "cooldown": 180.0,
                "volatility_z_max": 2.5,
                "displacement_z_max": 3.0,
                "absorption_score_min": 0.3,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0012,
                "max_break_age": 60.0,
                "cvd_divergence_threshold": 0.35,
            },
            "liquidity_exhaustion": {
                "min_tests": 3,
                "declining_threshold": 0.75,
                "min_bounce_pct": 0.0010,
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
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.40, "regime": 0.30, "structure": 0.15, "liquidity": 0.10, "spread": 0.05},
            "grade_thresholds": {"A": 0.70, "B": 0.40},
        },
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.040},
            "failed_breakout": {"tp_pct": 0.010, "sl_pct": 0.010},
            "liquidity_exhaustion": {"tp_pct": 0.010, "sl_pct": 0.010},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.040},
        },
        "guardians": {
            "l2_ratio_min": 0.8,
            "l2_ratio_min_trend_down": 2.2,
            "spread_max_ratio": 2.0,
        },
    },
    # =========================================================================
    # THIN_VOLATILE — BNB
    # Thin book, moderate vol
    # Conservative entries, wider stops
    # =========================================================================
    "THIN_VOLATILE": {
        "description": "Thin book + vol moderada — XRP, DOGE",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 1.5,
                "concentration_min": 0.40,
                "noise_max": 0.35,
                "stagnation_floor_pct": 0.15,
                "cooldown": 150.0,
                "volatility_z_max": 3.0,
                "displacement_z_max": 3.5,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0010,
                "max_break_age": 90.0,
                "cvd_divergence_threshold": 0.30,
            },
            "liquidity_exhaustion": {
                "min_tests": 3,
                "declining_threshold": 0.75,
                "min_bounce_pct": 0.0015,
                "test_memory_seconds": 150.0,
            },
            "trend_acceptance": {
                "min_candles_outside": 3,
                "cvd_confirmation_threshold": 4.5,
                "pullback_tolerance_pct": 0.0015,
                "max_pullback_penetration_pct": 0.0015,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.30, "regime": 0.30, "structure": 0.20, "liquidity": 0.15, "spread": 0.05},
            "grade_thresholds": {"A": 0.65, "B": 0.40},
        },
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.040},
            "failed_breakout": {"tp_pct": 0.010, "sl_pct": 0.010},
            "liquidity_exhaustion": {"tp_pct": 0.010, "sl_pct": 0.010},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.040},
        },
        "guardians": {
            "l2_ratio_min": 1.0,
            "l2_ratio_min_trend_down": 1.5,
            "spread_max_ratio": 2.5,
        },
    },
    # =========================================================================
    # ILLIQUID_SPEC — Ilíquido / especulativo
    # Basado en VOLATIL_BAJO_FLOW (penúltima iteración)
    # SL amplios (4-5%), per-regime asimétrico
    # =========================================================================
    "ILLIQUID_SPEC": {
        "description": "Ilíquido / especulativo — parámetros VOLATIL_BAJO_FLOW validados",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.5,
                "concentration_min": 0.40,
                "noise_max": 0.40,
                "stagnation_floor_pct": 0.08,
                "cooldown": 120.0,
                "volatility_z_max": 3.5,
                "displacement_z_max": 3.5,
            },
            "failed_breakout": {
                "min_break_distance_pct": 0.0008,
                "max_break_age": 90.0,
                "cvd_divergence_threshold": 0.25,
            },
            "liquidity_exhaustion": {
                "min_tests": 3,
                "declining_threshold": 0.75,
                "min_bounce_pct": 0.0010,
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
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.40, "regime": 0.30, "structure": 0.15, "liquidity": 0.10, "spread": 0.05},
            "grade_thresholds": {"A": 0.70, "B": 0.40},
        },
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.040},
            "failed_breakout": {"tp_pct": 0.010, "sl_pct": 0.010},
            "liquidity_exhaustion": {"tp_pct": 0.010, "sl_pct": 0.010},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.040},
        },
        "guardians": {
            "l2_ratio_min": 0.5,
            "l2_ratio_min_trend_down": 2.0,
            "spread_max_ratio": 2.0,
        },
    },
}

DEFAULT_PROFILE = "MID_LIQUID"
