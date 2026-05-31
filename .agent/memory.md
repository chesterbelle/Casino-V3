# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Quality Pipeline + Exhaustion Core + Profile System.
*   **Current Branch**: `v8.4-agent-friendly-refactor` (v8.4 Crystal Reforge, commit `432ab03`)
*   **Active Mode**: Multi-Coin with Profile-Based Adaptation
*   **Active Alpha**: **AMT V10 Alpha** (Profile-Optimized).


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

### 1. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA 🟢]
*   **Architecture**: Quality Pipeline + 4 scenarios + exhaustion gate + dynamic targets + profile system
*   **Profiles**: VOLATIL_BAJO_FLOW (SUI, AVAX, LTC), EFICIENTE_MEGACAP (BTC, ETH), BALANCED_MID (SOL, ADA, BNB, LINK, DOGE)
*   **Métrica Forense (LTCUSDT 24h)**: Net Taker +0.06%, MFE/MAE 1.63, Win Rate 59.8%
*   **Multi-Coin**: 3/10 coins con edge (SUI, AVAX, LTC). Edge instrument-dependiente.
*   **Exhaustion Gate**: Bloquea agresores intensificándose (delta_ratio > 1.5)
*   **Target Proximity**: 0.83 avg, 68.6% achieved

### 2. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **Profile System**: coin_profiler.py + profile_manager.py + config/coin_profiles.py
*   **Quality Scoring**: 5 factores ponderados, grade A/B/None
*   **Dynamic Targets**: TP/SL por perfil y escenario
*   **Guardianes**: L2 ratio y spread thresholds por perfil

### 3. Capa de Acero (Resiliencia / Ejecución) — [CERTIFICADA ✅]
*   **Slim Exit Engine (v10.2)**: Scale Out + Micro-Z Reversal
*   **Audit Mode**: In-trade lock bypass + no execution
*   **Proximity Analysis**: Muestra qué tan cerca están los targets

---

## 📉 Roadmap
1.  **CRYSTAL REFORGE — COMPLETADO ✅**: Quality Pipeline + Profile System implementado
2.  **FILTRO DE RÉGIMEN — COMPLETADO ✅**: Macro direction directo para l2_ratio_min + slow drift 60c
3.  **BEAR GAP FIX — COMPLETADO ✅**: Macro override (score≥0.6 bypassa síntesis), threshold 0.25, confidence 0.85, absorption threshold 1.8σ, slow drift 120c. BEAR_Apr24 L/S 1.31→0.49 🎯.
4.  **POC-BASED DYNAMIC TARGETS — COMPLETADO ✅**: TP = POC distance (avg 2.15%, dinámico), SL = 1.5% fijo. V2 Net Taker +0.8527%. Global Net Taker +0.6546% 🔥.
5.  **VALIDAR SUI/AVAX — PRÓXIMO**: Mismo perfil VOLATIL_BAJO_FLOW. Verificar que POC-based targets funcionan.
6.  **FILTRO DE LIQUIDEZ — PENDIENTE**: Activar/desactivar absorción según profundidad total del order book
7.  **DOWNLOAD MORE DATASETS — PENDIENTE**: Descargar días adicionales para tuning
8.  **CROSS-VALIDATION — PENDIENTE**: Validar robustez de parámetros por perfil
9.  **MULTI-ASSET TUNING — PENDIENTE**: Optimizar perfiles con más datos
10. **INVESTIGACIÓN ETH — PENDIENTE**: Investigar por qué ETH no logra Net Taker positivo
11. **LIVE / PAPER TRADING — PENDIENTE**: Conexión al Testnet/Live

---

### Current Status: 🟢 v8.4 Crystal Reforge + POC-Based Dynamic Targets ✅
- **Architecture**: Quality Pipeline + 4 scenarios + exhaustion gate + dynamic POC-targets + coin profiler + profile manager + proximity analysis + regime filter + macro override.
- **Baseline**: Net Taker +0.6546% (LTC 9 datasets, 1,810 signals). Gross Expectancy +0.7746%. MFE/MAE 1.29, WR 65.2%.
- **POC-Based TP**: TP = distancia al POC por trade (dinámico, avg 2.15%). SL = 1.5% fijo (per profile). V2 Net Taker +0.8527% 🔥.
- **BEAR Gap Fix**: BEAR_Apr24 L/S ratio ↓ 1.31→0.87 (intacto tras cambios de targets).
- **Root Cause**: RESUELTA — POC-based dynamic targets transformaron V2 de -0.0867% a +0.8527% Net Taker.
- **MarketRegimeSensor**: Macro override (score≥0.6 bypassa síntesis), threshold macro-alone 0.25, confidence escalation 0.85, absorption threshold 1.8σ, slow drift 60c + 120c.
- **Tags**: `v8.4-agent-friendly-refactor` (current).
- **Profiles**: 3 comprehensivos (VOLATIL_BAJO_FLOW, EFICIENTE_MEGACAP, BALANCED_MID) con TODOS los parámetros de Crystal Layer.
- **Per Setup**: TacticalAbsorptionV2 (MFE/MAE 1.29, Net +0.8527% ✅), failed_breakout (MFE/MAE 0.91, Net +0.0325% ✅), liquidity_exhaustion (MFE/MAE 0.50, Net -0.2100% ❌), trend_acceptance (MFE/MAE 1.17, Net -0.0153% ❌)
- **Multi-Coin**: 3/10 coins con edge (SUI, AVAX, LTC).
- **Profile Changelog**: `.agent/perfil_changelog.md` — historial de iteraciones y hallazgos.
- **Next**: Validar SUI/AVAX con POC-based targets, optimizar liquidity_exhaustion/trend_acceptance, investigar BEAR_Oct24/Feb25

---

## ⚠️ Gotchas Críticos
10. **Taker-Only Execution Mandate**: Toda validación se juzga descontando fees Taker del 0.12%.
11. **Historian Cumulative Runs**: Usar `--historian-db` para aislar archivos SQLite por run.
12. **Parallel Audit SQLite Write Locks**: Usar archivos temporales y consolidar al final.
13. **Break-Even Cost Fallacy**: El Break-Even estático mata el Edge (93.75% winners perdidos). Todo SL debe ser estructural.

---

## 📝 Timeline de Sesiones Recientes
- 2026-05-30T20:30:00 | session-close | POC-Based Dynamic Targets: TP = POC distance (avg 2.15%), SL = 1.5%. V2 Net Taker +0.8527% 🔥. Global Net Taker +0.6546%. El mejor resultado histórico. La sesión más productiva del proyecto: de -0.0791% a +0.6546% (+0.7337pp).
- 2026-05-30T17:30:00 | session-close | BEAR Gap Fix completo: macro override, threshold 0.25, confidence 0.85, absorption 1.8σ, slow drift 120c. BEAR_Apr24 L/S 1.31→0.49 🎯. Gross Expectancy +0.0409% (positiva primera vez). Net Taker -0.0791%. Root cause: TARGET FAILURE.
- 2026-05-30T06:00:00 | session-close | MarketRegimeSensor improvements: slow drift 60c + macro direction para l2_ratio_min + net direction ratio. Net Taker mejoró de -0.0625% a -0.0321% (+0.0304%). failed_breakout ahora positivo (+0.0040%).
- 2026-05-30T01:00:00 | session-investigation | L2 Depth Audit: Thin Wall (MFE/MAE 2.16) > High Wall (1.23) en RANGE/BULL. OPUESTO en BEAR: High Wall (1.49) > Thin Wall (0.48). Absorption funciona cuando hay liquidez pasiva suficiente.
- 2026-05-30T00:30:00 | session-update | Profile iteration: 5 configs probadas. Mejor resultado -0.0464% Net Taker. BEAR arrastra resultado global (-0.0822%). Problema es estrategia, no perfil.
- 2026-05-28T09:00:00 | session-close | v8.4 Crystal Reforge implementado: Quality Pipeline + Exhaustion Core. 177 signals, 37% WR, Net Taker +0.0012%. Necesita threshold tuning.
- 2026-05-28T06:00:00 | session-update | Edge Audit LTCUSDT: 3 signals, Net Taker +0.1739%. Diagnóstico: 98.7% guardian rejection rate (195/198).
- 2026-05-28T06:30:00 | session-update | Forense guardian chain: 917 ABS signals → 229 guardian rejections → 723 passed → 720 killed by in-trade lock → 3 trades.
- 2026-05-28T07:00:00 | session-update | TOXIC FLOW BLOCK identificado como bug de diseño: contradice BALANCE regime (score=1.0) y TREND Cases 3/4.
- 2026-05-28T07:30:00 | session-update | A/B test: eliminar toxic block → Signals 3→11 (+267%), Net Taker +0.17%→+0.66% (+283%), MFE/MAE 0.92→1.81.
- 2026-05-28T08:00:00 | session-update | Audit mode fixes: in-trade lock bypass + no execution. FADE RISK analysis: sensor VAH/UX filter reverted (arquitectura incorrecta).
- 2026-05-28T08:30:00 | session-close | v8.4-crystal-reforge tagged. Net Taker +0.68%, MFE/MAE 1.62, WR 100%. 3 commits, 0 regress.
- 2026-05-27T16:00:00 | session-update | Crystal Layer Cleanup: Auditoría forense identificó AbsorptionReversalGuardian desconectado, fast_track zombie, código muerto acumulado V8→V10.
- 2026-05-27T16:30:00 | session-update | Ejecutado benchmark pre-cleanup: 2 signals, Net Taker +0.1334%, Net Maker +0.1734%.
- 2026-05-27T17:00:00 | session-close | Cleanup completado: -2,172 líneas, 6 archivos eliminados, 8 archivos podados. Post-cleanup: Net Taker +0.1155%, Net Maker +0.1555%.
- 2026-05-27T18:00:00 | session-update | Crystal Layer 10/10 Readability: regime_guardian decomuesto (297→167), ES→EN, Phase numbers eliminados, code quality.
- 2026-05-27T19:00:00 | session-update | AMT V10 Manifesto + docs: CONFIGURATION.md (527), TROUBLESHOOTING.md (620).
- 2026-05-27T20:00:00 | session-update | Iron Layer OPT (16 OPT across 10 files): backtest 33% faster, live latency reduced.
- 2026-05-27T21:00:00 | session-update | Validator fixes: 3 fixed, 1 deleted, 10/10 PASS. validate-all.md v8.5.
- 2026-05-27T22:00:00 | session-update | Edge auditor: calibrator removed (250 lines). 3 workflows updated. merge_historian.py verified.
- 2026-05-27T22:16:00 | session-close | Full session documented. 18 commits, -2,857 líneas netas, Net Taker +0.1334% preservado. Commit `f036fbd`.


## v8.5-fixed (Fixed Targets 2.4%/2.5%)

**Retracción completa de v8.5-profitable (POC-based TP).**

### El Bug del Expectancy con TP Variable
- El auditor usaba `WR% × AvgTP_overall − (1−WR%) × AvgSL` para calcular expectancy.
- Con TP fijo, esta fórmula es correcta (TP constante para todos los trades).
- Con POC-based TP (TP = POC distance por trade), la fórmula es **incorrecta** porque:
  - Las trades que ganan tienen POC cerca → TP pequeño (avg 0.68%)
  - Las trades que pierden/expiran tienen POC lejano → TP grande (avg 3.7%)
  - `AvgTP_overall` (2.15%) incluye TPs de señales que NUNCA ganan, inflando la expectancy
- **Expectancy real de POC-based**: −0.14% Net (con cálculo per-signal correcto)

### Por qué POC-based no funciona
- Solo **45.3%** de los trades alcanzan su POC distance (MFE ≥ POC)
- Las ganadoras rinden 0.68% avg; las perdedoras pierden 1.5-2.5%
- R:R de ~0.45:1 no alcanza ni con 67.8% WR

### Solución: Targets Fijos TP=2.4% SL=2.5%
- V2: 303W 221L 972TO, WR 57.8%, **Net +0.2134%** ✅
- Overall (todos los setups): **Net +0.1248%** ✅
- El cálculo es exacto porque TP y SL son constantes

### Por régimen (targets fijos)
| Régimen | Mejor Fixed | Net |
|---------|------------|-----|
| RANGE   | TP=2.7% SL=2.5% | +0.53% |
| BULL    | TP=2.7% SL=2.5% | +0.63% |
| BEAR    | todos negativos | -0.03% |
| BEAR (POC>2.87%) | TP=3.0% SL=2.5% | +1.05% |

### Archivos modificados
- `decision/engine/targets.py`: removido POC-based TP override (líneas 64-67)
- `config/coin_profiles.py`: `tp_pct: 0.009→0.024`, `sl_pct: 0.015→0.025`

### Lecciones aprendidas
1. **No usar TP dinámico** con N pequeño y distribución sesgada — el expectancy es imposible de calcular correctamente sin per-signal PnL
2. **Targets fijos son más robustos** y su evaluación es determinista
3. **RANGE y BULL** son buenos para V2; **BEAR** es estructuralmente negativo — requiere filtrado por POC distance
4. **Desde AMT**, BEAR/BULL son trending simétricos — no tratarlos diferente
