"""
Auto-generated Coin Profiles by Profile Auditor
Based on analysis of 10 coins × 24h historical data
"""

# Correlations between microstructure and edge
CORRELATIONS = {
    "trades_per_sec_vs_mfe_mae_ratio": -0.394,
    "trades_per_sec_vs_net_taker": -0.285,
    "trades_per_sec_vs_has_edge": -0.602,
    "atr_pct_vs_mfe_mae_ratio": 0.614,
    "atr_pct_vs_net_taker": 0.737,
    "atr_pct_vs_has_edge": 0.371,
    "volume_24h_usd_vs_mfe_mae_ratio": 0.57,
    "volume_24h_usd_vs_net_taker": 0.714,
    "volume_24h_usd_vs_has_edge": 0.338,
}

# Tier thresholds (auto-calibrated)
TIER_THRESHOLDS = {
    "TIER_1": {
        "trade_density": [0.028, 0.036],
        "volume_24h": [76080755.112, 198007630.022],
        "description": "Edge exists, moderate flow",
    },
    "TIER_2": {
        "trade_density": [0.036, 0.072],
        "volume_24h": [198007630.022, 594022890.066],
        "description": "Marginal edge, higher flow",
    },
    "TIER_3": {
        "trade_density": [0.072, 100],
        "volume_24h": [594022890.066, 1000000000000],
        "description": "No edge, too efficient",
    },
}

# Coin assignments (auto-detected from historical data)
COIN_ASSIGNMENTS = {
    "SOL/USDT:USDT": "TIER_3",
    "ADA/USDT:USDT": "TIER_3",
    "BNB/USDT:USDT": "TIER_3",
    "ETH/USDT:USDT": "TIER_3",
    "BTC/USDT:USDT": "TIER_3",
    "AVAX/USDT:USDT": "TIER_1",
    "LINK/USDT:USDT": "TIER_1",
    "DOGE/USDT:USDT": "TIER_3",
    "LTC/USDT:USDT": "TIER_1",
    "SUI/USDT:USDT": "TIER_1",
}

# Profile multipliers
TIER_MULTIPLIERS = {
    "TIER_1": {"tp": 1.0, "sl": 1.0, "quality_bonus": 0.1},
    "TIER_2": {"tp": 0.8, "sl": 0.8, "quality_bonus": 0.0},
    "TIER_3": {"tp": 0.5, "sl": 0.5, "quality_penalty": -0.2},
}
