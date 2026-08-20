# Reporte de Análisis de Drawdown y Riesgo (Fase 1.6)
**Fecha**: 2026-08-20
**Herramienta**: `scripts/drawdown_analyzer.py`

## 📈 Riesgo Global (Portafolio de 8 activos)
*   **Max Drawdown**: **0.24%** (Extremadamente bajo, límite en roadmap era < 20%).
*   **Total Return**: +0.63% en la ventana probada (237 trades).
*   **Win Rate Global**: 66.0% con un Risk/Reward de 1.20.
*   **Rachas de pérdidas (Loss Streak)**: Máxima de **9 trades consecutivos**. Tiempo promedio de recuperación: 8.7 trades.

## 💰 Recomendación de Capital y Tamaño de Posición
Basado en el requisito mínimo de Binance ($20 de notional por orden):
*   **Riesgo por trade recomendado**: 1% a 3%.
*   **Capital mínimo requerido** (al 1% de riesgo): **$2,000**.
*   **Capital mínimo requerido** (al 3% de riesgo): **$667**.
*   Incluso a 3% de riesgo por trade, el Max Drawdown estimado escala a apenas ~0.72%, dejando mucho margen de seguridad hasta el límite de 5%.

## 📋 Desglose por Activo
| Symbol | Trades | WR% | Net PnL | Max Loss | Avg Win | Avg Loss |
|--------|--------|-----|---------|----------|---------|----------|
| ADAUSDT | 48 | 75.7% | +$19.24 | -$1.64 | +$1.25 | -$1.61 |
| OPUSDT | 14 | 78.6% | +$17.15 | -$2.16 | +$1.87 | -$1.15 |
| DOGEUSDT | 45 | 100.0%| +$16.10 | -$2.55 | +$2.36 | $0.00 |
| AVAXUSDT | 19 | 71.4% | +$12.73 | -$2.65 | +$2.37 | -$2.65 |
| XRPUSDT | 22 | 59.1% | +$6.95 | -$2.66 | +$2.37 | -$2.65 |
| LINKUSDT | 7 | 71.4% | +$5.25 | -$1.35 | +$1.59 | -$1.35 |
| LTCUSDT | 18 | 56.2% | -$0.68 | -$1.04 | +$0.54 | -$0.87 |
| BNBUSDT | 64 | 53.1% | -$14.16 | -$1.05 | +$0.44 | -$0.97 |

*(Nota: SOLUSDT fue procesado pero no generó señales materializadas en esta muestra específica).*

## 🏁 Veredicto
**✅ PASSED**. El riesgo estructural del portafolio al 1-3% de riesgo por posición es muy conservador (Max DD < 5%). Listo para avanzar a la Fase 1.7 (Auditoría de Readiness para Paper Trading).
