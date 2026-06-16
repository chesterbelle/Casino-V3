"""Optimized for THIN_VOLATILE - Recovered from DB"""

COIN_PROFILES = {
    "MEGA_LIQUID": {
        "description": "Mid-cap alta liquidez \u2014 ADA, ARB, NEAR",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.0,
                "concentration_min": 0.6,
                "noise_max": 0.25,
                "stagnation_floor_pct": 0.12,
                "cooldown": 300.0,
                "volatility_z_max": 2.0,
                "displacement_z_max": 2.0,
                "absorption_score_min": 0.5,
            },
            "failed_breakout": {
                "cooldown": 120.0,
                "min_break_distance_pct": 0.0005,
                "max_break_age": 45.0,
                "cvd_divergence_threshold": 0.35,
            },
            "liquidity_exhaustion": {
                "cooldown": 60.0,
                "level_tolerance_pct": 0.0003,
                "min_tests": 4,
                "declining_threshold": 0.7,
                "min_bounce_pct": 0.0005,
                "test_memory_seconds": 90.0,
            },
            "trend_acceptance": {
                "cooldown": 600.0,
                "min_candles_outside": 4,
                "cvd_confirmation_threshold": 6.0,
                "pullback_tolerance_pct": 0.0008,
                "max_pullback_penetration_pct": 0.0008,
            },
        },
        "scenarios": {"enabled": ["tactical_absorption", "liquidity_exhaustion", "trend_acceptance"]},
        "quality_scorer": {
            "weights": {"exhaustion": 0.4, "regime": 0.3, "structure": 0.15, "liquidity": 0.1, "spread": 0.05},
            "grade_thresholds": {"A": 0.8, "B": 0.5},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"strong": 2.0, "adequate": 1.5, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.0},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.04},
            "failed_breakout": {"tp_pct": 0.01, "sl_pct": 0.01},
            "liquidity_exhaustion": {"tp_pct": 0.01, "sl_pct": 0.01},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.04},
        },
        "guardians": {"l2_ratio_min": 2.5, "spread_max_ratio": 1.5},
    },
    "MAJOR_LIQUID": {
        "description": "Large-cap alta liquidez \u2014 SOL",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 1.8,
                "concentration_min": 0.55,
                "noise_max": 0.3,
                "stagnation_floor_pct": 0.1,
            },
            "failed_breakout": {
                "cooldown": 60.0,
                "min_break_distance_pct": 0.0006,
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
                "min_candles_outside": 3,
                "cvd_confirmation_threshold": 5.0,
                "pullback_tolerance_pct": 0.001,
                "max_pullback_penetration_pct": 0.001,
            },
        },
        "scenarios": {
            "enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.35, "regime": 0.28, "structure": 0.17, "liquidity": 0.12, "spread": 0.08},
            "grade_thresholds": {"A": 0.7, "B": 0.45},
            "thresholds": {
                "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
                "liquidity": {"strong": 2.0, "adequate": 1.5, "weak": 1.0},
                "structure": {"excess_multiplier": 0.5},
            },
        },
        "pressure_thresholds": {"z_block": 2.0},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.04},
            "failed_breakout": {"tp_pct": 0.01, "sl_pct": 0.01},
            "liquidity_exhaustion": {"tp_pct": 0.01, "sl_pct": 0.01},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.04},
        },
        "guardians": {"l2_ratio_min": 1.5, "l2_ratio_min_trend_down": 2.0, "spread_max_ratio": 1.8},
    },
    "MID_LIQUID": {
        "description": "Mid-cap, edge validado \u2014 LTC, AVAX, OP, APT, BNB, LINK",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.0,
                "concentration_min": 0.5,
                "noise_max": 0.4,
                "stagnation_floor_pct": 0.08,
                "cooldown": 180.0,
                "volatility_z_max": 2.5,
                "displacement_z_max": 3.0,
                "absorption_score_min": 0.3,
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
        "pressure_thresholds": {"z_block": 2.0},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.04},
            "failed_breakout": {"tp_pct": 0.01, "sl_pct": 0.01},
            "liquidity_exhaustion": {"tp_pct": 0.01, "sl_pct": 0.01},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.04},
        },
        "guardians": {"l2_ratio_min": 0.8, "l2_ratio_min_trend_down": 2.2, "spread_max_ratio": 2.0},
    },
    "THIN_VOLATILE": {
        "description": "Thin book + vol moderada \u2014 XRP, DOGE",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.5,
                "concentration_min": 0.9,
                "noise_max": 0.5,
                "stagnation_floor_pct": 0.16999999999999998,
                "cooldown": 120.0,
                "volatility_z_max": 2.0,
                "displacement_z_max": 1.5,
                "absorption_score_min": 0.7000000000000001,
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
        "guardians": {"l2_ratio_min": 2.8, "l2_ratio_min_trend_down": 1.9, "spread_max_ratio": 2.6},
    },
    "ILLIQUID_SPEC": {
        "description": "Alta actividad, libro menos profundo \u2014 BTC, ETH",
        "sensors": {
            "absorption_detector": {
                "z_score_min": 2.5,
                "concentration_min": 0.4,
                "noise_max": 0.4,
                "stagnation_floor_pct": 0.08,
                "cooldown": 120.0,
                "volatility_z_max": 3.5,
                "displacement_z_max": 3.5,
            },
            "failed_breakout": {
                "cooldown": 90.0,
                "min_break_distance_pct": 0.0008,
                "max_break_age": 90.0,
                "cvd_divergence_threshold": 0.25,
            },
            "liquidity_exhaustion": {
                "cooldown": 45.0,
                "level_tolerance_pct": 0.0008,
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
        "pressure_thresholds": {"z_block": 2.0},
        "targets": {
            "tactical_absorption": {"tp_pct": 0.025, "sl_pct": 0.04},
            "failed_breakout": {"tp_pct": 0.01, "sl_pct": 0.01},
            "liquidity_exhaustion": {"tp_pct": 0.01, "sl_pct": 0.01},
            "trend_acceptance": {"tp_pct": 0.025, "sl_pct": 0.04},
        },
        "guardians": {"l2_ratio_min": 0.5, "l2_ratio_min_trend_down": 2.0, "spread_max_ratio": 2.0},
    },
}

DEFAULT_PROFILE = "MID_LIQUID"
