#!/usr/bin/env python3
"""
Consolidate optimization results from multiple timeframes into a single config.
"""

# Results from optimization runs
RESULTS_1M = {
    "BollingerTouch": {"tp_pct": 0.0270, "sl_pct": 0.0140, "exp": 0.492},
    "EngulfingPattern": {"tp_pct": 0.0140, "sl_pct": 0.0220, "exp": 0.448},
    "KeltnerReversion": {"tp_pct": 0.0120, "sl_pct": 0.0270, "exp": 0.396},
    "ZScoreReversion": {"tp_pct": 0.0270, "sl_pct": 0.0260, "exp": 0.356},
    "CCIReversion": {"tp_pct": 0.0070, "sl_pct": 0.0300, "exp": 0.303},
    "StochasticReversion": {"tp_pct": 0.0080, "sl_pct": 0.0290, "exp": 0.286},
    "MomentumBurst": {"tp_pct": 0.0050, "sl_pct": 0.0270, "exp": 0.278},
    "EMA50Support": {"tp_pct": 0.0090, "sl_pct": 0.0180, "exp": 0.274},
    "WilliamsRReversion": {"tp_pct": 0.0080, "sl_pct": 0.0300, "exp": 0.250},
    "DecelerationCandles": {"tp_pct": 0.0070, "sl_pct": 0.0200, "exp": 0.238},
    "RailsPattern": {"tp_pct": 0.0060, "sl_pct": 0.0290, "exp": 0.210},
    "DojiIndecision": {"tp_pct": 0.0310, "sl_pct": 0.0080, "exp": 0.205},
    "RSIReversion": {"tp_pct": 0.0060, "sl_pct": 0.0300, "exp": 0.157},
    "Supertrend": {"tp_pct": 0.0040, "sl_pct": 0.0180, "exp": 0.148},
    "MACDCrossover": {"tp_pct": 0.0040, "sl_pct": 0.0270, "exp": 0.144},
    "PinBarReversal": {"tp_pct": 0.0050, "sl_pct": 0.0290, "exp": 0.122},
    "EMACrossover": {"tp_pct": 0.0050, "sl_pct": 0.0290, "exp": 0.112},
    "VolumeImbalance": {"tp_pct": 0.0050, "sl_pct": 0.0290, "exp": 0.107},
    "VCPPattern": {"tp_pct": 0.0080, "sl_pct": 0.0300, "exp": 0.078},
    "ExtremeCandleRatio": {"tp_pct": 0.0050, "sl_pct": 0.0280, "exp": 0.065},
    "FVGRetest": {"tp_pct": 0.0080, "sl_pct": 0.0190, "exp": 0.039},
    "InsideBarBreakout": {"tp_pct": 0.0060, "sl_pct": 0.0300, "exp": 0.034},
}

RESULTS_5M = {
    "BollingerTouch": {"tp_pct": 0.0770, "sl_pct": 0.0330, "exp": 0.372},
    "PinBarReversal": {"tp_pct": 0.0690, "sl_pct": 0.0290, "exp": 0.205},
    "BollingerSqueeze": {"tp_pct": 0.0230, "sl_pct": 0.0490, "exp": 0.193},
    "DojiIndecision": {"tp_pct": 0.0690, "sl_pct": 0.0350, "exp": 0.162},
    "VWAPDeviation": {"tp_pct": 0.0370, "sl_pct": 0.0490, "exp": 0.159},
    "Supertrend": {"tp_pct": 0.0610, "sl_pct": 0.0290, "exp": 0.154},
    "KeltnerReversion": {"tp_pct": 0.0790, "sl_pct": 0.0410, "exp": 0.152},
    "MorningStar": {"tp_pct": 0.0690, "sl_pct": 0.0370, "exp": 0.141},
    "CCIReversion": {"tp_pct": 0.0710, "sl_pct": 0.0470, "exp": 0.136},
    "StochasticReversion": {"tp_pct": 0.0690, "sl_pct": 0.0490, "exp": 0.104},
    "WilliamsRReversion": {"tp_pct": 0.0690, "sl_pct": 0.0490, "exp": 0.084},
    "ZScoreReversion": {"tp_pct": 0.0770, "sl_pct": 0.0330, "exp": 0.061},
    "InsideBarBreakout": {"tp_pct": 0.0730, "sl_pct": 0.0350, "exp": 0.057},
    "MACDCrossover": {"tp_pct": 0.0690, "sl_pct": 0.0350, "exp": 0.019},
}

RESULTS_15M = {
    "MorningStar": {"tp_pct": 0.1180, "sl_pct": 0.0250, "exp": 1.505},
    "BollingerSqueeze": {"tp_pct": 0.1090, "sl_pct": 0.0400, "exp": 1.453},
    "MomentumBurst": {"tp_pct": 0.1060, "sl_pct": 0.0250, "exp": 0.672},
    "VolumeImbalance": {"tp_pct": 0.1120, "sl_pct": 0.0490, "exp": 0.637},
    "Supertrend": {"tp_pct": 0.1150, "sl_pct": 0.0400, "exp": 0.630},
    "BollingerTouch": {"tp_pct": 0.0940, "sl_pct": 0.0160, "exp": 0.599},
    "RailsPattern": {"tp_pct": 0.1180, "sl_pct": 0.0370, "exp": 0.577},
    "EMACrossover": {"tp_pct": 0.1180, "sl_pct": 0.0280, "exp": 0.473},
    "ADXFilter": {"tp_pct": 0.0760, "sl_pct": 0.0790, "exp": 0.348},
    "FVGRetest": {"tp_pct": 0.1000, "sl_pct": 0.0310, "exp": 0.339},
    "PinBarReversal": {"tp_pct": 0.1180, "sl_pct": 0.0250, "exp": 0.326},
    "ExtremeCandleRatio": {"tp_pct": 0.1120, "sl_pct": 0.0250, "exp": 0.322},
    "ZScoreReversion": {"tp_pct": 0.0940, "sl_pct": 0.0160, "exp": 0.317},
    "MarubozuMomentum": {"tp_pct": 0.1180, "sl_pct": 0.0460, "exp": 0.279},
    "MACDCrossover": {"tp_pct": 0.1030, "sl_pct": 0.0340, "exp": 0.269},
    "DojiIndecision": {"tp_pct": 0.0760, "sl_pct": 0.0550, "exp": 0.251},
    "EMA50Support": {"tp_pct": 0.1120, "sl_pct": 0.0430, "exp": 0.248},
    "VCPPattern": {"tp_pct": 0.1180, "sl_pct": 0.0250, "exp": 0.199},
    "DecelerationCandles": {"tp_pct": 0.1180, "sl_pct": 0.0190, "exp": 0.185},
    "InsideBarBreakout": {"tp_pct": 0.1180, "sl_pct": 0.0250, "exp": 0.176},
    "CCIReversion": {"tp_pct": 0.1180, "sl_pct": 0.0190, "exp": 0.142},
    "RSIReversion": {"tp_pct": 0.1180, "sl_pct": 0.0220, "exp": 0.104},
    "KeltnerReversion": {"tp_pct": 0.1090, "sl_pct": 0.0100, "exp": 0.100},
    "VWAPDeviation": {"tp_pct": 0.0970, "sl_pct": 0.0520, "exp": 0.031},
    "WilliamsRReversion": {"tp_pct": 0.1180, "sl_pct": 0.0190, "exp": 0.009},
}

# Collect all unique sensors
all_sensors = set()
all_sensors.update(RESULTS_1M.keys())
all_sensors.update(RESULTS_5M.keys())
all_sensors.update(RESULTS_15M.keys())

print("# Multi-Timeframe Optimized Parameters")
print("# Generated automatically from optimization runs")
print("# Only includes sensors with positive expectancy\n")
print("SENSOR_PARAMS = {")

for sensor in sorted(all_sensors):
    print(f'    "{sensor}": {{')

    if sensor in RESULTS_1M:
        params = RESULTS_1M[sensor]
        print(
            f'        "1m": {{"tp_pct": {params["tp_pct"]:.4f}, "sl_pct": {params["sl_pct"]:.4f}}},  # Exp: {params["exp"]:.3f}%'
        )

    if sensor in RESULTS_5M:
        params = RESULTS_5M[sensor]
        print(
            f'        "5m": {{"tp_pct": {params["tp_pct"]:.4f}, "sl_pct": {params["sl_pct"]:.4f}}},  # Exp: {params["exp"]:.3f}%'
        )

    if sensor in RESULTS_15M:
        params = RESULTS_15M[sensor]
        print(
            f'        "15m": {{"tp_pct": {params["tp_pct"]:.4f}, "sl_pct": {params["sl_pct"]:.4f}}},  # Exp: {params["exp"]:.3f}%'
        )

    print("    },")

print("}")

print(f"\n# Total sensors optimized: {len(all_sensors)}")
print(f"# 1m: {len(RESULTS_1M)} sensors")
print(f"# 5m: {len(RESULTS_5M)} sensors")
print(f"# 15m: {len(RESULTS_15M)} sensors")
