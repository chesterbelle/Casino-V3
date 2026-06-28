# Auto-generated profile configs with va_gate
# Do not edit manually - use config/coin_profiles.py source

COIN_PROFILES = {
    "AVAX_NOISY_UNCERTAIN": {
        "description": "AVAX — extraído de NOISY_UNCERTAIN (builder), golden params",
        "guardians": {
            "l2_ratio_min": 0.8,
            "l2_ratio_min_tactical_absorption": 2.1,
            "l2_ratio_min_trend_acceptance": 1.5,
            "l2_ratio_min_trend_down": 2.2,
            "spread_max_ratio": 2.0,
        },
        "pressure_thresholds": {"z_block": 2.0},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.7, "B": 0.55},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"adequate": 1.5, "strong": 2.0, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {"exhaustion": 0.1, "liquidity": 0.1, "regime": 0.45, "spread": 0.05, "structure": 0.3},
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.001,
                "cooldown": 130.0,
                "displacement_z_max": 3.0,
                "stagnation_floor_pct": 0.0008,
                "volatility_z_max": 2.5,
                "z_score_min": 5.4,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "divergence_z": 0.4,
                "max_break_age": 60.0,
                "min_break_distance_pct": 0.002,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "declining_threshold": 0.8,
                "level_tolerance_pct": 0.0005,
                "min_bounce_pct": 0.002,
                "min_tests": 4,
                "test_memory_seconds": 120.0,
            },
            "trend_acceptance": {
                "cooldown": 600.0,
                "cvd_confirmation_threshold": 4.0,
                "max_pullback_penetration_pct": 0.003,
                "min_candles_outside": 5,
                "pullback_tolerance_pct": 0.001,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.04, "tp_pct": 0.02},
            "liquidity_exhaustion": {"sl_pct": 0.03, "tp_pct": 0.02},
            "tactical_absorption": {"sl_pct": 0.038, "tp_pct": 0.024},
            "trend_acceptance": {"sl_pct": 0.05, "tp_pct": 0.025},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "DOGE_BEHAVIOR": {
        "description": "Thin book + vol moderada — DOGE",
        "guardians": {
            "l2_ratio_min": 2.8,
            "l2_ratio_min_trend_acceptance": 2.0,
            "l2_ratio_min_trend_down": 1.9,
            "spread_max_ratio": 2.6,
        },
        "pressure_thresholds": {"z_block": 2.6},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.55, "B": 0.2},
            "thresholds": {
                "exhaustion": {"block": 2.9000000000000004, "perfect": 1.0, "vol_bonus": 0.7000000000000001},
                "liquidity": {"adequate": 0.75, "strong": 2.0, "weak": 1.5000000000000002},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {
                "exhaustion": 0.15000000000000002,
                "liquidity": 0.3,
                "regime": 0.30000000000000004,
                "spread": 0.06,
                "structure": 0.05,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.001,
                "cooldown": 120.0,
                "displacement_z_max": 1.5,
                "stagnation_floor_pct": 0.16999999999999998,
                "volatility_z_max": 2.0,
                "z_score_min": 2.5,
            },
            "failed_breakout": {
                "cooldown": 20.0,
                "divergence_z": 0.4,
                "max_break_age": 180.0,
                "min_break_distance_pct": 0.0019,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "declining_threshold": 0.55,
                "level_tolerance_pct": 0.0013000000000000002,
                "min_bounce_pct": 0.0011,
                "min_tests": 3,
                "test_memory_seconds": 170.0,
            },
            "trend_acceptance": {
                "cooldown": 330.0,
                "cvd_confirmation_threshold": 4.0,
                "max_pullback_penetration_pct": 0.0006000000000000001,
                "min_candles_outside": 4,
                "pullback_tolerance_pct": 0.002,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.022, "tp_pct": 0.019},
            "liquidity_exhaustion": {"sl_pct": 0.016, "tp_pct": 0.003},
            "tactical_absorption": {"sl_pct": 0.032, "tp_pct": 0.021},
            "trend_acceptance": {"sl_pct": 0.02, "tp_pct": 0.041},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "INERTIAL_TRENDING": {
        "description": "Trending — ETH, LINK",
        "guardians": {
            "l2_ratio_min": 1.8,
            "l2_ratio_min_trend_acceptance": 1.8,
            "l2_ratio_min_trend_down": 2.0,
            "spread_max_ratio": 2.0,
        },
        "pressure_thresholds": {"z_block": 2.2},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.65, "B": 0.4},
            "thresholds": {
                "exhaustion": {"block": 2.0, "perfect": 0.7, "vol_bonus": 0.5},
                "liquidity": {"adequate": 1.2, "strong": 2.0, "weak": 0.8},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {"exhaustion": 0.25, "liquidity": 0.15, "regime": 0.35, "spread": 0.1, "structure": 0.15},
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.0,
                "cooldown": 130.0,
                "displacement_z_max": 2.5,
                "level_tolerance_pct": 0.002,
                "stagnation_floor_pct": 0.0008,
                "volatility_z_max": 3.0,
                "z_score_min": 2.0,
            },
            "failed_breakout": {
                "cooldown": 45.0,
                "divergence_z": 0.35,
                "max_break_age": 120.0,
                "min_break_distance_pct": 0.001,
            },
            "liquidity_exhaustion": {
                "cooldown": 25.0,
                "declining_threshold": 0.65,
                "level_tolerance_pct": 0.0008,
                "min_bounce_pct": 0.001,
                "min_tests": 3,
                "test_memory_seconds": 120.0,
            },
            "trend_acceptance": {
                "cooldown": 450.0,
                "cvd_confirmation_threshold": 4.0,
                "max_pullback_penetration_pct": 0.002,
                "min_candles_outside": 4,
                "pullback_tolerance_pct": 0.0015,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.018, "tp_pct": 0.015},
            "liquidity_exhaustion": {"sl_pct": 0.025, "tp_pct": 0.018},
            "tactical_absorption": {"sl_pct": 0.035, "tp_pct": 0.022},
            "trend_acceptance": {"sl_pct": 0.035, "tp_pct": 0.03},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "LTC_NOISY_UNCERTAIN_1": {
        "description": "LTC — FB+LE+TAV+TA edge confirmed ✅. LE CVD flip fix, TP1.0/SL2.0.",
        "guardians": {
            "l2_ratio_min": 0.5,
            "l2_ratio_min_trend_acceptance": 1.2,
            "l2_ratio_min_trend_down": 2.2,
            "spread_max_ratio": 2.5,
        },
        "pressure_thresholds": {"z_block": 2.8},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.7, "B": 0.4},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"adequate": 1.5, "strong": 2.0, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {"exhaustion": 0.4, "liquidity": 0.1, "regime": 0.3, "spread": 0.05, "structure": 0.15},
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "absorption_score_min": 0.2,
                "book_bucket_pct": 0.001,
                "cooldown": 60.0,
                "displacement_z_max": 2.9,
                "level_tolerance_pct": 0.002,
                "stagnation_floor_pct": 0.0018,
                "volatility_z_max": 3.1,
                "z_score_min": 4.0,
            },
            "failed_breakout": {
                "cooldown": 55.0,
                "divergence_z": 1.1,
                "exhaustion_z": 3.9,
                "max_break_age": 160.0,
                "min_break_distance_pct": 0.0026,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "declining_threshold": 0.80,
                "level_tolerance_pct": 0.0005,
                "min_bounce_pct": 0.00075,
                "min_tests": 3,
                "test_memory_seconds": 60.0,
            },
            "trend_acceptance": {
                "cooldown": 600.0,
                "cvd_confirmation_threshold": 1.5,
                "max_pullback_penetration_pct": 0.001,
                "min_candles_outside": 3,
                "pullback_tolerance_pct": 0.001,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.04, "tp_pct": 0.025},
            "liquidity_exhaustion": {"sl_pct": 0.007, "tp_pct": 0.007},
            "tactical_absorption": {"sl_pct": 0.04, "tp_pct": 0.025},
            "trend_acceptance": {"sl_pct": 0.009, "tp_pct": 0.009},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "NOISY_UNCERTAIN": {
        "description": "Noisy — NEAR",
        "guardians": {
            "l2_ratio_min": 2.0,
            "l2_ratio_min_trend_acceptance": 2.0,
            "l2_ratio_min_trend_down": 2.5,
            "spread_max_ratio": 2.5,
        },
        "pressure_thresholds": {"z_block": 2.4},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.7, "B": 0.45},
            "thresholds": {
                "exhaustion": {"block": 2.5, "perfect": 0.8, "vol_bonus": 0.5},
                "liquidity": {"adequate": 1.5, "strong": 2.5, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {"exhaustion": 0.2, "liquidity": 0.15, "regime": 0.35, "spread": 0.1, "structure": 0.2},
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.001,
                "cooldown": 30.0,
                "displacement_z_max": 2.0,
                "level_tolerance_pct": 0.002,
                "stagnation_floor_pct": 0.0008,
                "volatility_z_max": 2.2,
                "z_score_min": 3.0,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "divergence_z": 0.45,
                "max_break_age": 90.0,
                "min_break_distance_pct": 0.0015,
            },
            "liquidity_exhaustion": {
                "cooldown": 40.0,
                "declining_threshold": 0.7,
                "level_tolerance_pct": 0.001,
                "min_bounce_pct": 0.0015,
                "min_tests": 4,
                "test_memory_seconds": 150.0,
            },
            "trend_acceptance": {
                "cooldown": 500.0,
                "cvd_confirmation_threshold": 5.0,
                "max_pullback_penetration_pct": 0.002,
                "min_candles_outside": 5,
                "pullback_tolerance_pct": 0.001,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.015, "tp_pct": 0.012},
            "liquidity_exhaustion": {"sl_pct": 0.02, "tp_pct": 0.01},
            "tactical_absorption": {"sl_pct": 0.025, "tp_pct": 0.015},
            "trend_acceptance": {"sl_pct": 0.03, "tp_pct": 0.02},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "NOISY_UNCERTAIN_1": {
        "description": "Thin book noisy — XRP, DOGE, BNB, BTC, ADA, APT, ARB, OP",
        "guardians": {
            "l2_ratio_min": 2.0,
            "l2_ratio_min_trend_acceptance": 2.0,
            "l2_ratio_min_trend_down": 2.2,
            "spread_max_ratio": 2.5,
        },
        "pressure_thresholds": {"z_block": 2.4},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.6, "B": 0.35},
            "thresholds": {
                "exhaustion": {"block": 2.2, "perfect": 0.6, "vol_bonus": 0.5},
                "liquidity": {"adequate": 1.2, "strong": 2.2, "weak": 0.8},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {"exhaustion": 0.25, "liquidity": 0.2, "regime": 0.3, "spread": 0.1, "structure": 0.15},
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.001,
                "cooldown": 180.0,
                "displacement_z_max": 2.5,
                "level_tolerance_pct": 0.002,
                "stagnation_floor_pct": 0.0008,
                "volatility_z_max": 2.5,
                "z_score_min": 2.5,
            },
            "failed_breakout": {
                "cooldown": 30.0,
                "divergence_z": 0.4,
                "max_break_age": 120.0,
                "min_break_distance_pct": 0.0015,
            },
            "liquidity_exhaustion": {
                "cooldown": 35.0,
                "declining_threshold": 0.6,
                "level_tolerance_pct": 0.001,
                "min_bounce_pct": 0.0012,
                "min_tests": 3,
                "test_memory_seconds": 150.0,
            },
            "trend_acceptance": {
                "cooldown": 400.0,
                "cvd_confirmation_threshold": 4.5,
                "max_pullback_penetration_pct": 0.001,
                "min_candles_outside": 4,
                "pullback_tolerance_pct": 0.0015,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.02, "tp_pct": 0.015},
            "liquidity_exhaustion": {"sl_pct": 0.02, "tp_pct": 0.012},
            "tactical_absorption": {"sl_pct": 0.03, "tp_pct": 0.018},
            "trend_acceptance": {"sl_pct": 0.03, "tp_pct": 0.025},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "SOL_INERTIAL_TRENDING": {
        "description": "SOL — extraído de INERTIAL_TRENDING (builder), golden params",
        "guardians": {
            "l2_ratio_min": 2.0,
            "l2_ratio_min_trend_acceptance": 2.0,
            "l2_ratio_min_trend_down": 2.0,
            "spread_max_ratio": 1.8,
        },
        "pressure_thresholds": {"z_block": 2.0},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.7, "B": 0.45},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"adequate": 1.5, "strong": 2.0, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {"exhaustion": 0.4, "liquidity": 0.12, "regime": 0.28, "spread": 0.08, "structure": 0.12},
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.0,
                "cooldown": 120.0,
                "displacement_z_max": 3.0,
                "level_tolerance_pct": 0.003,
                "stagnation_floor_pct": 0.1,
                "volatility_z_max": 2.5,
                "z_score_min": 2.0,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "divergence_z": 0.3,
                "max_break_age": 60.0,
                "min_break_distance_pct": 0.0001,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "declining_threshold": 0.72,
                "level_tolerance_pct": 0.0005,
                "min_bounce_pct": 0.0007,
                "min_tests": 3,
                "test_memory_seconds": 100.0,
            },
            "trend_acceptance": {
                "cooldown": 600.0,
                "cvd_confirmation_threshold": 4.0,
                "max_pullback_penetration_pct": 0.0025,
                "min_candles_outside": 5,
                "pullback_tolerance_pct": 0.0008,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.008, "tp_pct": 0.008},
            "liquidity_exhaustion": {"sl_pct": 0.007, "tp_pct": 0.007},
            "trend_acceptance": {"sl_pct": 0.008, "tp_pct": 0.008},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "THIN_VOLATILE": {
        "description": "Thin book + vol moderada — ADA, APT, ARB, BNB, BTC, ETH, LINK, NEAR, OP, LTC",
        "guardians": {
            "l2_ratio_min": 2.8,
            "l2_ratio_min_trend_acceptance": 2.0,
            "l2_ratio_min_trend_down": 1.9,
            "spread_max_ratio": 2.6,
        },
        "pressure_thresholds": {"z_block": 2.6},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.55, "B": 0.2},
            "thresholds": {
                "exhaustion": {"block": 2.9000000000000004, "perfect": 1.0, "vol_bonus": 0.7000000000000001},
                "liquidity": {"adequate": 0.75, "strong": 2.0, "weak": 1.5000000000000002},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {
                "exhaustion": 0.15000000000000002,
                "liquidity": 0.3,
                "regime": 0.30000000000000004,
                "spread": 0.06,
                "structure": 0.05,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.001,
                "cooldown": 120.0,
                "displacement_z_max": 1.5,
                "stagnation_floor_pct": 0.16999999999999998,
                "volatility_z_max": 2.0,
                "z_score_min": 2.5,
            },
            "failed_breakout": {
                "cooldown": 20.0,
                "divergence_z": 0.4,
                "max_break_age": 180.0,
                "min_break_distance_pct": 0.0019,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "declining_threshold": 0.55,
                "level_tolerance_pct": 0.0013000000000000002,
                "min_bounce_pct": 0.0011,
                "min_tests": 3,
                "test_memory_seconds": 170.0,
            },
            "trend_acceptance": {
                "cooldown": 330.0,
                "cvd_confirmation_threshold": 4.0,
                "max_pullback_penetration_pct": 0.0006000000000000001,
                "min_candles_outside": 4,
                "pullback_tolerance_pct": 0.002,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.022, "tp_pct": 0.019},
            "liquidity_exhaustion": {"sl_pct": 0.016, "tp_pct": 0.003},
            "tactical_absorption": {"sl_pct": 0.032, "tp_pct": 0.021},
            "trend_acceptance": {"sl_pct": 0.02, "tp_pct": 0.041},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
    "XRP_BEHAVIOR": {
        "description": "Thin book + vol moderada — XRP",
        "guardians": {
            "l2_ratio_min": 2.8,
            "l2_ratio_min_trend_acceptance": 2.0,
            "l2_ratio_min_trend_down": 1.9,
            "spread_max_ratio": 2.6,
        },
        "pressure_thresholds": {"z_block": 2.6},
        "quality_scorer": {
            "grade_thresholds": {"A": 0.55, "B": 0.2},
            "thresholds": {
                "exhaustion": {"block": 2.9000000000000004, "perfect": 1.0, "vol_bonus": 0.7000000000000001},
                "liquidity": {"adequate": 0.75, "strong": 2.0, "weak": 1.5000000000000002},
                "structure": {"excess_multiplier": 0.5},
            },
            "weights": {
                "exhaustion": 0.15000000000000002,
                "liquidity": 0.3,
                "regime": 0.30000000000000004,
                "spread": 0.06,
                "structure": 0.05,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "sensors": {
            "absorption_detector": {
                "book_bucket_pct": 0.001,
                "cooldown": 120.0,
                "displacement_z_max": 1.5,
                "stagnation_floor_pct": 0.16999999999999998,
                "volatility_z_max": 2.0,
                "z_score_min": 2.5,
            },
            "failed_breakout": {
                "cooldown": 20.0,
                "divergence_z": 0.4,
                "max_break_age": 180.0,
                "min_break_distance_pct": 0.0019,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "declining_threshold": 0.55,
                "level_tolerance_pct": 0.0013000000000000002,
                "min_bounce_pct": 0.0011,
                "min_tests": 3,
                "test_memory_seconds": 170.0,
            },
            "trend_acceptance": {
                "cooldown": 330.0,
                "cvd_confirmation_threshold": 4.0,
                "max_pullback_penetration_pct": 0.0006000000000000001,
                "min_candles_outside": 4,
                "pullback_tolerance_pct": 0.002,
            },
        },
        "targets": {
            "failed_breakout": {"sl_pct": 0.022, "tp_pct": 0.019},
            "liquidity_exhaustion": {"sl_pct": 0.016, "tp_pct": 0.003},
            "tactical_absorption": {"sl_pct": 0.032, "tp_pct": 0.021},
            "trend_acceptance": {"sl_pct": 0.02, "tp_pct": 0.041},
        },
        "va_gate": {
            "allow_in_trending": ["trend_acceptance"],
            "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
            "integrity_threshold": 0.15,
        },
    },
}

DEFAULT_PROFILE = "NOISY_UNCERTAIN_1"
