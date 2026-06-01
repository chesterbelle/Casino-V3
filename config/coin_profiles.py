"""
Coin Profiles — 5-tier Microstructure Classification
=====================================================

Replaces 3-profile system (VOLATIL_BAJO, EFICIENTE_MEGACAP, BALANCED_MID)
with 5 profiles classified by 5 microstructure dimensions:

  - spread_bps:        absolute spread in basis points (cost of liquidity)
  - depth_ratio:       bid_vol / ask_vol within 0.2% of mid (information in book)
  - speed:             trades per second (frequency of events)
  - avg_trade_size:    average USD per trade (retail vs institutional)
  - vol_realized_4h:   std of log returns over 4h candles (volatility regime)

Profiles:
  - MEGA_LIQUID:       BTC, ETH (institutional, ultra-deep)
  - MAJOR_LIQUID:      SOL, BNB, XRP (large-cap, high liquidity)
  - MID_LIQUID:        LTC, ADA, LINK, DOGE (mid-cap, edge validated)
  - THIN_VOLATILE:     AVAX, SUI, NEAR, APT, OP, ARB (thin book, high vol)
  - ILLIQUID_SPEC:     long-tail, new listings (disabled by default)
"""

COIN_PROFILES = {
    # =========================================================================
    # MEGA_LIQUID — BTC, ETH
    # Ultra-deep books, tight spreads, institutional flow
    # =========================================================================
    "MEGA_LIQUID": {
        "description": "Mega-cap institucional — BTC, ETH",
        "characteristics": {
            "spread_bps": {"min": 0.0, "max": 5.0},
            "depth_ratio": {"min": 0.0, "max": 100.0},
            "speed": {"min": 0.0, "max": 100.0},
            "avg_trade_size": {"min": 50000, "max": 1e9},
            "vol_realized_4h": {"min": 0.0, "max": 5.0},
        },
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.5,
                "concentration_min": 0.60,
                "noise_max": 0.25,
                "stagnation_floor_pct": 0.12,
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
            "enabled": ["TacticalAbsorptionV2"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.40, "regime": 0.30, "structure": 0.15, "liquidity": 0.10, "spread": 0.05},
            "grade_thresholds": {"A": 0.80, "B": 0.50},
        },
        "targets": {
            "TacticalAbsorptionV2": {"tp_pct": 0.005, "sl_pct": 0.005},
            "failed_breakout": {"tp_pct": 0.006, "sl_pct": 0.006},
            "liquidity_exhaustion": {"tp_pct": 0.004, "sl_pct": 0.004},
            "trend_acceptance": {"tp_pct": 0.006, "sl_pct": 0.006},
        },
        "guardians": {
            "l2_ratio_min": 2.5,
            "spread_max_ratio": 1.5,
        },
    },
    # =========================================================================
    # MAJOR_LIQUID — SOL, BNB, XRP
    # Large-cap, high liquidity, vol moderada
    # =========================================================================
    "MAJOR_LIQUID": {
        "description": "Large-cap alta liquidez — SOL, BNB, XRP",
        "characteristics": {
            "spread_bps": {"min": 0.0, "max": 15.0},
            "depth_ratio": {"min": 0.0, "max": 100.0},
            "speed": {"min": 0.0, "max": 100.0},
            "avg_trade_size": {"min": 5000, "max": 50000},
            "vol_realized_4h": {"min": 0.0, "max": 5.0},
        },
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.2,
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
            "enabled": ["TacticalAbsorptionV2", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.35, "regime": 0.28, "structure": 0.17, "liquidity": 0.12, "spread": 0.08},
            "grade_thresholds": {"A": 0.70, "B": 0.45},
        },
        "targets": {
            "TacticalAbsorptionV2": {
                "tp_pct": 0.015,
                "sl_pct": 0.015,
                "regime": {
                    "TREND_UP": {"tp_pct": 0.010, "sl_pct": 0.020},
                    "TREND_DOWN": {"tp_pct": 0.015, "sl_pct": 0.025},
                    "BALANCE": {"tp_pct": 0.007, "sl_pct": 0.020},
                },
            },
            "failed_breakout": {"tp_pct": 0.012, "sl_pct": 0.015},
            "liquidity_exhaustion": {"tp_pct": 0.010, "sl_pct": 0.005},
            "trend_acceptance": {"tp_pct": 0.012, "sl_pct": 0.012},
        },
        "guardians": {
            "l2_ratio_min": 1.5,
            "l2_ratio_min_trend_down": 1.8,
            "spread_max_ratio": 1.8,
        },
    },
    # =========================================================================
    # MID_LIQUID — LTC, ADA, LINK, DOGE
    # Mid-cap, parámetros validados en 6 datasets LTC (iter 3)
    # =========================================================================
    "MID_LIQUID": {
        "description": "Mid-cap, edge validado iter 3 — LTC, ADA, LINK, DOGE",
        "characteristics": {
            "spread_bps": {"min": 0.0, "max": 15.0},
            "depth_ratio": {"min": 0.0, "max": 100.0},
            "speed": {"min": 0.0, "max": 100.0},
            "avg_trade_size": {"min": 500, "max": 10000},
            "vol_realized_4h": {"min": 0.0, "max": 1.2},
        },
        "sensors": {
            "absorption_detector": {
                "z_score_min": 3.5,
                "concentration_min": 0.50,  # Iter2: 0.40→0.50
                "noise_max": 0.40,
                "stagnation_floor_pct": 0.08,
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
            "enabled": ["TacticalAbsorptionV2", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.4, "regime": 0.3, "structure": 0.15, "liquidity": 0.1, "spread": 0.05},
            "grade_thresholds": {"A": 0.7, "B": 0.4},
        },
        "targets": {
            "TacticalAbsorptionV2": {
                "tp_pct": 0.024,
                "sl_pct": 0.025,
                "regime": {  # Iter3 validated
                    "TREND_UP": {"tp_pct": 0.012, "sl_pct": 0.025},
                    "TREND_DOWN": {"tp_pct": 0.020, "sl_pct": 0.030},
                    "BALANCE": {"tp_pct": 0.008, "sl_pct": 0.025},
                },
            },
            "failed_breakout": {"tp_pct": 0.020, "sl_pct": 0.025},
            "liquidity_exhaustion": {"tp_pct": 0.015, "sl_pct": 0.004},
            "trend_acceptance": {"tp_pct": 0.009, "sl_pct": 0.009},
        },
        "guardians": {
            "l2_ratio_min": 0.5,  # Iter1 reverted
            "l2_ratio_min_trend_down": 2.0,
            "spread_max_ratio": 2.0,
        },
    },
    # =========================================================================
    # THIN_VOLATILE — AVAX, SUI, NEAR, APT, OP, ARB
    # Thin book, high vol. TAV/FB disabled (entry failure MFE/MAE < 1.2)
    # =========================================================================
    "THIN_VOLATILE": {
        "description": "Thin book + high vol — TAV/FB deshabilitados, solo LE/TA",
        "characteristics": {
            "spread_bps": {"min": 0.0, "max": 15.0},
            "depth_ratio": {"min": 0.0, "max": 100.0},
            "speed": {"min": 0.0, "max": 100.0},
            "avg_trade_size": {"min": 500, "max": 10000},
            "vol_realized_4h": {"min": 1.2, "max": 10.0},
        },
        "sensors": {
            "absorption_detector": {
                "z_score_min": 4.0,  # más estricto
                "concentration_min": 0.60,  # más estricto
                "noise_max": 0.35,
                "stagnation_floor_pct": 0.10,
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
            # ⚠️ TAV/FB deshabilitados (entry failure MFE/MAE < 1.2)
            "enabled": ["liquidity_exhaustion", "trend_acceptance"],
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.30, "regime": 0.30, "structure": 0.20, "liquidity": 0.15, "spread": 0.05},
            "grade_thresholds": {"A": 0.75, "B": 0.45},
        },
        "targets": {
            # TAV/FB heredan defaults pero no se usan
            "TacticalAbsorptionV2": {"tp_pct": 0.020, "sl_pct": 0.030},
            "failed_breakout": {"tp_pct": 0.020, "sl_pct": 0.025},
            "liquidity_exhaustion": {"tp_pct": 0.025, "sl_pct": 0.008},  # TP/SL más amplios
            "trend_acceptance": {"tp_pct": 0.015, "sl_pct": 0.015},
        },
        "guardians": {
            "l2_ratio_min": 0.7,
            "l2_ratio_min_trend_down": 2.5,
            "spread_max_ratio": 2.5,
        },
    },
    # =========================================================================
    # ILLIQUID_SPEC — long-tail, new listings
    # Deshabilitado por default (no se ejecuta nada)
    # =========================================================================
    "ILLIQUID_SPEC": {
        "description": "Ilíquido / especulativo — DESHABILITADO",
        "characteristics": {
            "spread_bps": {"min": 0.0, "max": 1000.0},
            "depth_ratio": {"min": 0.0, "max": 100.0},
            "speed": {"min": 0.0, "max": 100.0},
            "avg_trade_size": {"min": 0, "max": 500},
            "vol_realized_4h": {"min": 0.0, "max": 100.0},
        },
        "sensors": {
            "absorption_detector": {
                "z_score_min": 4.5,
                "concentration_min": 0.70,
                "noise_max": 0.40,
                "stagnation_floor_pct": 0.15,
            },
        },
        "scenarios": {
            "enabled": [],  # nada habilitado
        },
        "quality_scorer": {
            "weights": {"exhaustion": 0.20, "regime": 0.20, "structure": 0.20, "liquidity": 0.20, "spread": 0.20},
            "grade_thresholds": {"A": 0.90, "B": 0.70},
        },
        "targets": {},
        "guardians": {
            "l2_ratio_min": 3.0,
            "spread_max_ratio": 1.0,
        },
    },
}

# Default profile for unknown coins (conservative)
DEFAULT_PROFILE = "MID_LIQUID"
