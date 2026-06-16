"""Auto-generated optimized profile for LTC_NOISY_UNCERTAIN_1"""

COIN_PROFILES = {
    "SOL_INERTIAL_TRENDING": {
        "description": "SOL \u2014 extra\u00eddo de INERTIAL_TRENDING (builder), golden params",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.0,
                "stagnation_floor_pct": 0.1,
                "cooldown": 120.0,
                "volatility_z_max": 2.5,
                "displacement_z_max": 3.0,
                "level_tolerance_pct": 0.003,
                "book_bucket_pct": 0.0,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "min_break_distance_pct": 0.0001,
                "max_break_age": 60.0,
                "cvd_divergence_threshold": 0.3,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "level_tolerance_pct": 0.0005,
                "min_tests": 3,
                "declining_threshold": 0.72,
                "min_bounce_pct": 0.0007,
                "test_memory_seconds": 100.0,
            },
            "trend_acceptance": {
                "cooldown": 600.0,
                "min_candles_outside": 5,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.0008,
                "max_pullback_penetration_pct": 0.0025,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.4, "regime": 0.28, "structure": 0.12, "liquidity": 0.12, "spread": 0.08},
            "grade_thresholds": {"A": 0.7, "B": 0.45},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"strong": 2.0, "adequate": 1.5, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.0},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.05},
            "failed_breakout": {"tp_pct": 0.01, "sl_pct": 0.01},
            "liquidity_exhaustion": {"tp_pct": 0.025, "sl_pct": 0.05},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.04},
        },
        "guardians": {
            "l2_ratio_min": 1.5,
            "l2_ratio_min_trend_down": 2.0,
            "l2_ratio_min_trend_acceptance": 2.0,
            "spread_max_ratio": 1.8,
        },
    },
    "AVAX_NOISY_UNCERTAIN": {
        "description": "AVAX \u2014 extra\u00eddo de NOISY_UNCERTAIN (builder), golden params",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 5.4,
                "stagnation_floor_pct": 0.0008,
                "cooldown": 130.0,
                "volatility_z_max": 2.5,
                "displacement_z_max": 3.0,
                "book_bucket_pct": 0.001,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "min_break_distance_pct": 0.002,
                "max_break_age": 60.0,
                "cvd_divergence_threshold": 0.4,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "level_tolerance_pct": 0.0005,
                "min_tests": 4,
                "declining_threshold": 0.8,
                "min_bounce_pct": 0.002,
                "test_memory_seconds": 120.0,
            },
            "trend_acceptance": {
                "cooldown": 600.0,
                "min_candles_outside": 5,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.001,
                "max_pullback_penetration_pct": 0.003,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.1, "regime": 0.45, "structure": 0.3, "liquidity": 0.1, "spread": 0.05},
            "grade_thresholds": {"A": 0.7, "B": 0.55},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"strong": 2.0, "adequate": 1.5, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.0},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.024, "sl_pct": 0.038},
            "failed_breakout": {"tp_pct": 0.02, "sl_pct": 0.04},
            "liquidity_exhaustion": {"tp_pct": 0.02, "sl_pct": 0.03},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.05},
        },
        "guardians": {
            "l2_ratio_min": 0.8,
            "l2_ratio_min_trend_down": 2.2,
            "l2_ratio_min_trend_acceptance": 1.5,
            "spread_max_ratio": 2.0,
            "l2_ratio_min_tactical_absorption": 2.1,
        },
    },
    "INERTIAL_TRENDING": {
        "description": "Trending \u2014 ETH, LINK",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.0,
                "stagnation_floor_pct": 0.0008,
                "cooldown": 130.0,
                "volatility_z_max": 3.0,
                "displacement_z_max": 2.5,
                "level_tolerance_pct": 0.002,
                "book_bucket_pct": 0.0,
            },
            "failed_breakout": {
                "cooldown": 45.0,
                "min_break_distance_pct": 0.001,
                "max_break_age": 120.0,
                "cvd_divergence_threshold": 0.35,
            },
            "liquidity_exhaustion": {
                "cooldown": 25.0,
                "level_tolerance_pct": 0.0008,
                "min_tests": 3,
                "declining_threshold": 0.65,
                "min_bounce_pct": 0.001,
                "test_memory_seconds": 120.0,
            },
            "trend_acceptance": {
                "cooldown": 450.0,
                "min_candles_outside": 4,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.0015,
                "max_pullback_penetration_pct": 0.002,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.25, "regime": 0.35, "structure": 0.15, "liquidity": 0.15, "spread": 0.1},
            "grade_thresholds": {"A": 0.65, "B": 0.4},
            "thresholds": {
                "exhaustion": {"block": 2.0, "perfect": 0.7, "vol_bonus": 0.5},
                "liquidity": {"strong": 2.0, "adequate": 1.2, "weak": 0.8},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.2},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.022, "sl_pct": 0.035},
            "failed_breakout": {"tp_pct": 0.015, "sl_pct": 0.018},
            "liquidity_exhaustion": {"tp_pct": 0.018, "sl_pct": 0.025},
            "trend_acceptance": {"tp_pct": 0.03, "sl_pct": 0.035},
        },
        "guardians": {
            "l2_ratio_min": 1.8,
            "l2_ratio_min_trend_down": 2.0,
            "l2_ratio_min_trend_acceptance": 1.8,
            "spread_max_ratio": 2.0,
        },
    },
    "NOISY_UNCERTAIN": {
        "description": "Noisy \u2014 NEAR",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.0,
                "stagnation_floor_pct": 0.0008,
                "cooldown": 30.0,
                "volatility_z_max": 2.2,
                "displacement_z_max": 2.0,
                "level_tolerance_pct": 0.002,
                "book_bucket_pct": 0.001,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "min_break_distance_pct": 0.0015,
                "max_break_age": 90.0,
                "cvd_divergence_threshold": 0.45,
            },
            "liquidity_exhaustion": {
                "cooldown": 40.0,
                "level_tolerance_pct": 0.001,
                "min_tests": 4,
                "declining_threshold": 0.7,
                "min_bounce_pct": 0.0015,
                "test_memory_seconds": 150.0,
            },
            "trend_acceptance": {
                "cooldown": 500.0,
                "min_candles_outside": 5,
                "cvd_confirmation_threshold": 5.0,
                "pullback_tolerance_pct": 0.001,
                "max_pullback_penetration_pct": 0.002,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.2, "regime": 0.35, "structure": 0.2, "liquidity": 0.15, "spread": 0.1},
            "grade_thresholds": {"A": 0.7, "B": 0.45},
            "thresholds": {
                "exhaustion": {"block": 2.5, "perfect": 0.8, "vol_bonus": 0.5},
                "liquidity": {"strong": 2.5, "adequate": 1.5, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.4},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.015, "sl_pct": 0.025},
            "failed_breakout": {"tp_pct": 0.012, "sl_pct": 0.015},
            "liquidity_exhaustion": {"tp_pct": 0.01, "sl_pct": 0.02},
            "trend_acceptance": {"tp_pct": 0.02, "sl_pct": 0.03},
        },
        "guardians": {
            "l2_ratio_min": 2.0,
            "l2_ratio_min_trend_down": 2.5,
            "l2_ratio_min_trend_acceptance": 2.0,
            "spread_max_ratio": 2.5,
        },
    },
    "LTC_NOISY_UNCERTAIN_1": {
        "description": "LTC \u2014 golden params (MID_LIQUID base + TA targets 0.9% fijados + spread 2.4)",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 6.0,
                "stagnation_floor_pct": 0.00030000000000000003,
                "cooldown": 70.0,
                "volatility_z_max": 1.9,
                "displacement_z_max": 3.7,
                "level_tolerance_pct": 0.002,
                "book_bucket_pct": 0.001,
                "absorption_score_min": 0.30000000000000004,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "min_break_distance_pct": 0.0012,
                "max_break_age": 60.0,
                "cvd_divergence_threshold": 0.35,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "level_tolerance_pct": 0.0005,
                "min_tests": 3,
                "declining_threshold": 0.75,
                "min_bounce_pct": 0.001,
                "test_memory_seconds": 120.0,
            },
            "trend_acceptance": {
                "cooldown": 600.0,
                "min_candles_outside": 3,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.001,
                "max_pullback_penetration_pct": 0.001,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.4, "regime": 0.3, "structure": 0.15, "liquidity": 0.1, "spread": 0.05},
            "grade_thresholds": {"A": 0.7, "B": 0.4},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"strong": 2.0, "adequate": 1.5, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 4.0},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.04},
            "failed_breakout": {"tp_pct": 0.01, "sl_pct": 0.01},
            "liquidity_exhaustion": {"tp_pct": 0.01, "sl_pct": 0.01},
            "trend_acceptance": {"tp_pct": 0.009, "sl_pct": 0.009},
        },
        "guardians": {
            "l2_ratio_min": 0.6,
            "l2_ratio_min_trend_down": 2.2,
            "l2_ratio_min_trend_acceptance": 1.5,
            "spread_max_ratio": 2.9000000000000004,
        },
    },
    "NOISY_UNCERTAIN_1": {
        "description": "Thin book noisy \u2014 XRP, DOGE, BNB, BTC, ADA, APT, ARB, OP",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.5,
                "stagnation_floor_pct": 0.0008,
                "cooldown": 180.0,
                "volatility_z_max": 2.5,
                "displacement_z_max": 2.5,
                "level_tolerance_pct": 0.002,
                "book_bucket_pct": 0.001,
            },
            "failed_breakout": {
                "cooldown": 30.0,
                "min_break_distance_pct": 0.0015,
                "max_break_age": 120.0,
                "cvd_divergence_threshold": 0.4,
            },
            "liquidity_exhaustion": {
                "cooldown": 35.0,
                "level_tolerance_pct": 0.001,
                "min_tests": 3,
                "declining_threshold": 0.6,
                "min_bounce_pct": 0.0012,
                "test_memory_seconds": 150.0,
            },
            "trend_acceptance": {
                "cooldown": 400.0,
                "min_candles_outside": 4,
                "cvd_confirmation_threshold": 4.5,
                "pullback_tolerance_pct": 0.0015,
                "max_pullback_penetration_pct": 0.001,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.25, "regime": 0.3, "structure": 0.15, "liquidity": 0.2, "spread": 0.1},
            "grade_thresholds": {"A": 0.6, "B": 0.35},
            "thresholds": {
                "exhaustion": {"block": 2.2, "perfect": 0.6, "vol_bonus": 0.5},
                "liquidity": {"strong": 2.2, "adequate": 1.2, "weak": 0.8},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.4},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.018, "sl_pct": 0.03},
            "failed_breakout": {"tp_pct": 0.015, "sl_pct": 0.02},
            "liquidity_exhaustion": {"tp_pct": 0.012, "sl_pct": 0.02},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.03},
        },
        "guardians": {
            "l2_ratio_min": 2.0,
            "l2_ratio_min_trend_down": 2.2,
            "l2_ratio_min_trend_acceptance": 2.0,
            "spread_max_ratio": 2.5,
        },
    },
    "XRP_BEHAVIOR": {
        "description": "Thin book + vol moderada \u2014 XRP",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.5,
                "stagnation_floor_pct": 0.16999999999999998,
                "cooldown": 120.0,
                "volatility_z_max": 2.0,
                "displacement_z_max": 1.5,
                "book_bucket_pct": 0.001,
            },
            "failed_breakout": {
                "cooldown": 20.0,
                "min_break_distance_pct": 0.0019,
                "max_break_age": 180.0,
                "cvd_divergence_threshold": 0.4,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "level_tolerance_pct": 0.0013000000000000002,
                "min_tests": 3,
                "declining_threshold": 0.55,
                "min_bounce_pct": 0.0011,
                "test_memory_seconds": 170.0,
            },
            "trend_acceptance": {
                "cooldown": 330.0,
                "min_candles_outside": 4,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.002,
                "max_pullback_penetration_pct": 0.0006000000000000001,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {
                "exhaustion": 0.15000000000000002,
                "regime": 0.30000000000000004,
                "structure": 0.05,
                "liquidity": 0.3,
                "spread": 0.06,
            },
            "grade_thresholds": {"A": 0.55, "B": 0.2},
            "thresholds": {
                "exhaustion": {"block": 2.9000000000000004, "perfect": 1.0, "vol_bonus": 0.7000000000000001},
                "liquidity": {"strong": 2.0, "adequate": 0.75, "weak": 1.5000000000000002},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.6},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.021, "sl_pct": 0.032},
            "failed_breakout": {"tp_pct": 0.019, "sl_pct": 0.022},
            "liquidity_exhaustion": {"tp_pct": 0.003, "sl_pct": 0.016},
            "trend_acceptance": {"tp_pct": 0.041, "sl_pct": 0.02},
        },
        "guardians": {
            "l2_ratio_min": 2.8,
            "l2_ratio_min_trend_down": 1.9,
            "l2_ratio_min_trend_acceptance": 2.0,
            "spread_max_ratio": 2.6,
        },
    },
    "DOGE_BEHAVIOR": {
        "description": "Thin book + vol moderada \u2014 DOGE",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.5,
                "stagnation_floor_pct": 0.16999999999999998,
                "cooldown": 120.0,
                "volatility_z_max": 2.0,
                "displacement_z_max": 1.5,
                "book_bucket_pct": 0.001,
            },
            "failed_breakout": {
                "cooldown": 20.0,
                "min_break_distance_pct": 0.0019,
                "max_break_age": 180.0,
                "cvd_divergence_threshold": 0.4,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "level_tolerance_pct": 0.0013000000000000002,
                "min_tests": 3,
                "declining_threshold": 0.55,
                "min_bounce_pct": 0.0011,
                "test_memory_seconds": 170.0,
            },
            "trend_acceptance": {
                "cooldown": 330.0,
                "min_candles_outside": 4,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.002,
                "max_pullback_penetration_pct": 0.0006000000000000001,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {
                "exhaustion": 0.15000000000000002,
                "regime": 0.30000000000000004,
                "structure": 0.05,
                "liquidity": 0.3,
                "spread": 0.06,
            },
            "grade_thresholds": {"A": 0.55, "B": 0.2},
            "thresholds": {
                "exhaustion": {"block": 2.9000000000000004, "perfect": 1.0, "vol_bonus": 0.7000000000000001},
                "liquidity": {"strong": 2.0, "adequate": 0.75, "weak": 1.5000000000000002},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.6},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.021, "sl_pct": 0.032},
            "failed_breakout": {"tp_pct": 0.019, "sl_pct": 0.022},
            "liquidity_exhaustion": {"tp_pct": 0.003, "sl_pct": 0.016},
            "trend_acceptance": {"tp_pct": 0.041, "sl_pct": 0.02},
        },
        "guardians": {
            "l2_ratio_min": 2.8,
            "l2_ratio_min_trend_down": 1.9,
            "l2_ratio_min_trend_acceptance": 2.0,
            "spread_max_ratio": 2.6,
        },
    },
    "THIN_VOLATILE": {
        "description": "Thin book + vol moderada \u2014 ADA, APT, ARB, BNB, BTC, ETH, LINK, NEAR, OP, LTC",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.5,
                "stagnation_floor_pct": 0.16999999999999998,
                "cooldown": 120.0,
                "volatility_z_max": 2.0,
                "displacement_z_max": 1.5,
                "book_bucket_pct": 0.001,
            },
            "failed_breakout": {
                "cooldown": 20.0,
                "min_break_distance_pct": 0.0019,
                "max_break_age": 180.0,
                "cvd_divergence_threshold": 0.4,
            },
            "liquidity_exhaustion": {
                "cooldown": 30.0,
                "level_tolerance_pct": 0.0013000000000000002,
                "min_tests": 3,
                "declining_threshold": 0.55,
                "min_bounce_pct": 0.0011,
                "test_memory_seconds": 170.0,
            },
            "trend_acceptance": {
                "cooldown": 330.0,
                "min_candles_outside": 4,
                "cvd_confirmation_threshold": 4.0,
                "pullback_tolerance_pct": 0.002,
                "max_pullback_penetration_pct": 0.0006000000000000001,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {
                "exhaustion": 0.15000000000000002,
                "regime": 0.30000000000000004,
                "structure": 0.05,
                "liquidity": 0.3,
                "spread": 0.06,
            },
            "grade_thresholds": {"A": 0.55, "B": 0.2},
            "thresholds": {
                "exhaustion": {"block": 2.9000000000000004, "perfect": 1.0, "vol_bonus": 0.7000000000000001},
                "liquidity": {"strong": 2.0, "adequate": 0.75, "weak": 1.5000000000000002},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.6},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.021, "sl_pct": 0.032},
            "failed_breakout": {"tp_pct": 0.019, "sl_pct": 0.022},
            "liquidity_exhaustion": {"tp_pct": 0.003, "sl_pct": 0.016},
            "trend_acceptance": {"tp_pct": 0.041, "sl_pct": 0.02},
        },
        "guardians": {
            "l2_ratio_min": 2.8,
            "l2_ratio_min_trend_down": 1.9,
            "l2_ratio_min_trend_acceptance": 2.0,
            "spread_max_ratio": 2.6,
        },
    },
}

DEFAULT_PROFILE = "NOISY_UNCERTAIN_1"
