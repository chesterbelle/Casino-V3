
[1m[96m======================================================================
  ANALYZING 2 SIGNALS (Dynamic Window per Setup)
======================================================================[0m
  Windows: TacticalAbsorptionV2=14400s, absorption_reversal=14400s, failed_breakout=7200s (and 2 more)

[1m[1] SETUP EDGE BREAKDOWN (Raw MFE/MAE) (Per Coin)[0m
Setup Type           Coin                       n      Avg MFE%   Avg MAE%   Ratio    Window
----------------------------------------------------------------------------------------------------
TacticalAbsorptionV2 LTC/USDT:USDT              1         0.616%    1.137% [91m  0.54[0m  14400s
liquidity_exhaustion LTC/USDT:USDT              1         0.617%    0.041% [92m 15.00[0m  7200s

[1m[2] ENTRY QUALITY ASSESSMENT (Uniform Grid as Ground Truth) (Per Coin)[0m
  The Uniform Grid tests ALL possible TP/SL combinations. If NONE produce
  positive Net Taker, the entry signal ITSELF has no exploitable edge,
  regardless of target optimization.

Setup Type           Coin                       Best TP/SL   Best WR%  Best Exp%   Best Net   Entry OK?
------------------------------------------------------------------------------------------------------------------------
TacticalAbsorptionV2 LTC/USDT:USDT              0.60/0.60%     100.0%    +0.6000%   +0.4800%  [92m✅ YES[0m
liquidity_exhaustion LTC/USDT:USDT              0.60/0.60%     100.0%    +0.6000%   +0.4800%  [92m✅ YES[0m

[1m[3] ROOT CAUSE DIAGNOSIS[0m

  [1mTacticalAbsorptionV2 / LTC/USDT:USDT[0m (n=1)
    MFE/MAE Ratio:     0.54 ❌ (need >1.2 for directional edge)
    Best Uniform:      0.60/0.60% → Exp +0.6000%
    Best Net Taker:    +0.4800% ✅
    AMT Targets:       Exp +0.1917% (-0.41% vs best uniform)
    [93mVERDICT: TARGET OPTIMIZATION NEEDED ⚠️[0m
    AMT targets underperform the best uniform. Adjust formula.

  [1mliquidity_exhaustion / LTC/USDT:USDT[0m (n=1)
    MFE/MAE Ratio:     15.00 ✅ (need >1.2 for directional edge)
    Best Uniform:      0.60/0.60% → Exp +0.6000%
    Best Net Taker:    +0.4800% ✅
    AMT Targets:       Exp +0.3151% (-0.28% vs best uniform)
    [93mVERDICT: TARGET OPTIMIZATION NEEDED ⚠️[0m
    AMT targets underperform the best uniform. Adjust formula.

[1m[4] DECISION TRACE AUDIT (SetupEngine Gates)[0m
Gate                      Reason                                   Count
---------------------------------------------------------------------------
REGIME_ALIGNMENT_V3       Rejected by Guardian chain               196
SetupEngine               Rejected by Guardian chain               34
REGIME_ALIGNMENT_V3       Trade ready: AMT_TACTICALABSORPTIONV2_IN_VALUE 1
SetupEngine               Trade ready: AMT_LIQUIDITY_EXHAUSTION_OUT_OF_VALUE 1

[1m[5] REAL STRATEGY PERFORMANCE (Dynamic AMT Targets) (Per Coin)[0m
  Reference only — conclusion in [3] above determines if targets are the problem.
Setup Type           Coin                       n      W     L     TO    WR%      Avg TP%   Avg SL%   Exp%       Net Taker
----------------------------------------------------------------------------------------------------------------------------------
TacticalAbsorptionV2 LTC/USDT:USDT              1      1     0     0      100.0%    0.192%    0.111%   +0.1917%  [92m +0.0717%[0m
liquidity_exhaustion LTC/USDT:USDT              1      1     0     0      100.0%    0.315%    0.100%   +0.3151%  [92m +0.1951%[0m

[1m[6] ALPHA FUSION & CONVICTION AUDIT (Arbitrator Efficacy) (Per Coin)[0m
Coin                       Class                     n      W     L     WR%      Avg Conviction  Verdict
--------------------------------------------------------------------------------------------------------------
LTC/USDT:USDT              SOLO (Single)                  2      2     0     [92m 100.0%[0m       50.0        -

[1m[7] OVERALL EDGE SUMMARY[0m
----------------------------------------------------------------------
Total Signals:        2 (1 coins)
Decided (W+L):        2 (Timeouts: 0)
Overall Win Rate:     100.0%

[1mGross Expectancy:     +0.2534%[0m
Net (Taker 0.12%):    +0.1334% ✅
Net (Maker 0.08%):    +0.1734% ✅

[93m⚠️  ROOT CAUSE: TARGET FAILURE[0m
[93m   Entry has potential but AMT targets underperform best uniform.[0m
[93m   Adjust target formula (see Section [3] for details).[0m

[1mPer-Coin Summary[0m
Coin                       n      W     L     TO    WR%      Exp%       Net Taker  Verdict
---------------------------------------------------------------------------------------------------------
LTC/USDT:USDT              2      2     0     0     100.0%   +0.2534%  [92m +0.1334%[0m  [92mEDGE ✅[0m

[1m[96m======================================================================
  AUDIT COMPLETE
======================================================================[0m
