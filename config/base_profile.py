"""
Plantilla Base para Perfiles
Provee la estructura de llaves por defecto para evitar KeyErrors.
"""

BASE_TEMPLATE = {
    "description": "BASE_TEMPLATE - DO NOT USE DIRECTLY",
    "guardians": {
        "l2_ratio_min": 2.0,
        "l2_ratio_min_failed_breakout": 0.7,
        "l2_ratio_min_liquidity_exhaustion": 0.6,
        "l2_ratio_min_tactical_absorption": 0.6,
        "l2_ratio_min_trend_acceptance": 2.0,
        "l2_ratio_min_trend_down": 2.0,
        "spread_max_ratio": 1.8,
        "spread_max_ratio_failed_breakout": 2.2,
        "spread_max_ratio_liquidity_exhaustion": 3.1,
        "spread_max_ratio_tactical_absorption": 1.7,
        "spread_max_ratio_trend_acceptance": 2.1,
    },
    "optimization_status": {
        "date": "1970-01-01",
        "is_certified": False,
        "method": "none",
        "notes": "Plantilla estructural base.",
    },
    "pressure_thresholds": {
        "z_block": 2.0,
        "z_block_failed_breakout": 2.4,
        "z_block_liquidity_exhaustion": 2.4,
        "z_block_tactical_absorption": 2.4,
        "z_block_trend_acceptance": 2.7,
    },
    "quality_scorer": {
        "grade_thresholds": {"A": 0.7, "B": 0.45},
        "thresholds": {
            "exhaustion": {"block": 1.5, "perfect": 0.5, "vol_bonus": 0.4},
            "liquidity": {"adequate": 1.5, "strong": 2.0, "weak": 1.0},
            "structure": {"excess_multiplier": 0.5},
        },
        "weights": {"exhaustion": 0.4, "liquidity": 0.12, "regime": 0.28, "spread": 0.08, "structure": 0.12},
    },
    "scenarios": {"enabled": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]},
    "sensors": {
        "absorption_detector": {
            "absorption_score_min": 0.22500000000000003,
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
            "exhaustion_z": 2.4,
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
            "regime_poc_migration_max": 0.005,
            "regime_va_expansion_max": 1.1,
            "regime_vol_ratio_max": 1.5,
        },
    },
    "targets": {
        "failed_breakout": {"sl_pct": 0.005, "tp_pct": 0.05},
        "liquidity_exhaustion": {"sl_pct": 0.05, "tp_pct": 0.05},
        "tactical_absorption": {"sl_pct": 0.02, "tp_pct": 0.02},
        "trend_acceptance": {"sl_pct": 0.01, "tp_pct": 0.05},
    },
    "va_gate": {
        "allow_in_trending": ["trend_acceptance"],
        "block_in_range": ["trend_acceptance"],
        "block_in_trending": ["tactical_absorption", "failed_breakout", "liquidity_exhaustion"],
        "integrity_threshold": 0.15,
        "poc_migration_threshold": 0.003,
        "va_abs_width_threshold": 1.5,
        "va_expansion_threshold": 1.05,
        "vol_ratio_threshold": 1.3,
    },
}
