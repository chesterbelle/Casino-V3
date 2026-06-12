"""
=============================================================
📊 CLUSTER CONSTANTS — Normalization Bounds
=============================================================
"""

# Static Dimensions (used by CoinProfiler and Sensors)
STATIC_NORM_MIN = {
    "tick_size_efficiency": 0.0,
    "book_density": 0.0,
    "volume_vol_ratio": 0.0,
    "speed": 0.0,
    "micro_volatility": 0.0,
}
STATIC_NORM_MAX = {
    "tick_size_efficiency": 1.0,
    "book_density": 25.0,
    "volume_vol_ratio": 18.0,
    "speed": 500.0,
    "micro_volatility": 1.0,
}

# Behavioral Dimensions (used by Behavioral Cluster Builder)
BEHAVIORAL_NORM_MIN = {
    "eff_abs": 0.0,
    "vel_rev": 0.0,
    "pers_brk": 0.0,
}
BEHAVIORAL_NORM_MAX = {
    "eff_abs": 1.0,
    "vel_rev": 1000.0,
    "pers_brk": 1.0,
}
