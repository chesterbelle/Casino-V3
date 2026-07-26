# Golden Parameters: BNBUSDT (MID_LIQUID Fast-Track)

**Certificación:** 2026-07-23 (Fast-Track method)
**Template:** LTCUSDT (MID_LIQUID)
**Datasets:** 6
**Size:** 599 MB (Incluye 1 dataset pesado de 321MB `2026-02-06`)

## 1. Audit Resultados (Baseline Config)
- **Total Signals:** 212
- **Win Rate:** 57.5% (W: 122, L: 62, TO: 28)
- **Net Taker Baseline:** +0.1638% ✅

## 2. Target Diagnostics
El Edge Auditor reveló que el edge direccional inicial tenía targets insuficientes, perdiendo rentabilidad frente al **Best Static Grid**:

### failed_breakout
- MFE/MAE Ratio: 3.15 ✅
- Best Static Grid: 2.50/2.50% (Exp: +1.2490%)

### liquidity_exhaustion
- MFE/MAE Ratio: 2.16 ✅
- Best Static Grid: 2.00/0.30% (Exp: +1.1350%)

### tactical_absorption
- MFE/MAE Ratio: 0.67 ❌ (Sin edge direccional puro en este setup)
- Best Static Grid: 1.90/0.20% (Exp: +0.1500%)

### trend_acceptance
- MFE/MAE Ratio: 3.04 ✅
- Best Static Grid: 2.50/2.50% (Exp: +0.9545%)

## 3. Acciones Tomadas
1. Se clonó la matriz de LTCUSDT.
2. Se ajustaron las matrices de TP/SL en `config/coin_profiles.py` para BNBUSDT de acuerdo al Best Static Grid.
