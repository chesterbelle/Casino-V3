# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.
> 5. **REGLA DEL EDGE (NUNCA RENDIRSE):** NUNCA concluyas que "el edge no existe" o "ENTRY FAILURE" como veredicto final. Si no encontramos edge, es porque no hemos ajustado los parámetros correctos — seguimos ajustando sensores, targets, regímenes e infraestructura hasta que aparezca. No existen alphas muertas, solo parámetros no encontrados.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Quality Pipeline + Exhaustion Core + Profile System.
*   **Current Branch**: `8.7-cluster-improved` (V2 regime sensor — Price Action + Volume Profile + Markov)
*   **Active Mode**: Multi-Coin with Profile-Based Adaptation
*   **Active Alpha**: **AMT V10 Alpha** (Profile-Optimized).


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

### 1. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA 🟢]
*   **Architecture**: Quality Pipeline + 4 scenarios + exhaustion gate + dynamic targets + profile system
*   **Profiles**: 5 perfiles microestructura — MEGA_LIQUID (ADA, ARB, NEAR), MAJOR_LIQUID (SOL), MID_LIQUID (LTC, AVAX, OP, APT, BNB, LINK), THIN_VOLATILE (XRP, DOGE), ILLIQUID_SPEC (BTC, ETH)
*   **ILLIQUID_SPEC Backtest** (2026-06-02): SOL +0.24% Net Taker (edge marginal), XRP -0.05%, DOGE -0.13%. Solo SOL tiene potencial. **PERO**: profile system los clasifica como MAJOR_LIQUID, no ILLIQUID_SPEC — contradicción con clustering real.
*   **Métrica Forense (LTCUSDT 24h)**: Net Taker +0.06%, MFE/MAE 1.63, Win Rate 59.8%
*   **Multi-Coin**: 3/10 coins con edge (SUI, AVAX, LTC). Edge instrument-dependiente.
*   **Exhaustion Gate**: Bloquea agresores intensificándose (delta_ratio > 1.5)
*   **Target Proximity**: 0.83 avg, 68.6% achieved

### 2. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **Profile System v3**: coin_profiler.py (centroid-based) + profile_manager.py + config/coin_profiles.py + config/clusters.json
*   **Clustering**: K-Means con 4 dimensiones institucionales (tick_size_efficiency, book_density, volume_vol_ratio, speed)
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
4.  **PER-REGIME TARGETS — COMPLETADO ✅**: TP/SL asimétricos por régimen. V2 Set A +0.456%, Set B +0.482%.
5.  **AUTOPSIA TREND_DOWN — COMPLETADO ✅**: LONGS en TREND_DOWN = 6% WR (tóxico). Hard block revertido — no mata edge de SHORTS.
6.  **PROFILE VALIDATION VOLATIL_BAJO_FLOW — COMPLETADO ✅** (2026-06-01): 6 iteraciones + baseline. **Ganador: iter 3** (TAV SL tightening 2.5/3.0/2.5%). Net Taker **+0.0455%** (de -0.1066% baseline).
7.  **PROFILE SYSTEM V3 — COMPLETADO ✅** (2026-06-01): Rediseño a 4 dimensiones institucionales. Clustering K-Means automático desde exchange. Silhouette 0.538.
8.  **ILLIQUID_SPEC BACKTEST — COMPLETADO ✅** (2026-06-02): SOL +0.24% (edge marginal), XRP -0.05%, DOGE -0.13%. **PROBLEMA**: Profile contradiction — clustering no produce ILLIQUID_SPEC naturalmente.
9.  **RESOLVER PROFILE CONTRADICTION — PRÓXIMO 🔴**: K-Means no-determinista produce clusters diferentes cada corrida. SOL/XRP/DOGE clasificados como MAJOR_LIQUID por diagnostic pero THIN/MID por clustering. Necesitar: approach determinista para clustering o redefinición de perfiles.
10. **INVESTIGAR LONGS EN TREND_DOWN — RESUELTO 🟢** (2026-06-03): Root cause identificado: quality scorer permitía señales contra-tendencia con B-grade aunque regime guardian las rechazara (peso 25% permitía bypass). Solución: counter-trend penalty en quality_scorer.py — si regime_score==0.0, requiere A-grade (≥0.70) mínimo. Verificado que no hay bug de inversión — el disparity 6% vs 92% es estructural, no matemático.
11. **REDUCIR TIMEOUT RATE — PRÓXIMO 🔴**: Optimizar targets para bajar ~60% timeout. Es el drag principal.
12. **RE-EVALUAR NOMBRE DEL SETUP — PRÓXIMO**: TacticalAbsorptionV2 → InstitutionalFlowV2?
13. **ARQUITECTURA ENTRY — PRÓXIMO 🔴** (descubierto en iter 6): AVAX TAV y SUI TAV son **ENTRY FAILURE**. No se puede fix con parámetros. Requiere cambios en entry logic.
14. **FILTRO DE LIQUIDEZ — PENDIENTE**: Activar/desactivar absorción según profundidad total del order book
15. **CROSS-VALIDATION — PENDIENTE**: Validar robustez de parámetros por perfil
16. **INVESTIGACIÓN ETH — PENDIENTE**: Investigar por qué ETH no logra Net Taker positivo
17. **LIVE / PAPER TRADING — PENDIENTE**: Conexión al Testnet/Live
18. **FILTRO DIRECCIONAL THIN_VOLATILE — PRÓXIMO 🔴** (descubierto 2026-06-03): Auditor reveló DOGE TAV LONG Ratio 0.70 vs SHORT 1.05; XRP TAV LONG 0.97 vs SHORT 0.80. Asimetría direccional sistemática en thin books. Propuesta: filtro direccional por activo/perfil para deshabilitar LONG en ciertos regímenes. **SCOPE**: Fuera del alcance de parameter tuning — requiere cambios en entry logic del engine.
19. **REGIME SENSOR V2 — COMPLETADO ✅** (2026-06-04): Arquitectura 2-capas (Price Action + Volume Profile) + Markov memory. Accuracy 41.3% → **72.3%**. TREND_UP 42.2% → **78.0%**. Balance 16% → **60%**. Ambas capas contribuyen 98%+. Swing detection relajado (ANY en vez de BOTH). Commits: `e9dfd80`, `080e465`, `09cc9d5`.
20. **VERIFICAR INTEGRIDAD DE NUEVA ARQUITECTURA (PRESSURE ENGINE) — COMPLETADO ✅**: Los 4 escenarios migrados (`LiquidityExhaustion`, `FailedBreakout`, `TrendAcceptance`, `TacticalAbsorptionV2`) producen señales consistentes. Bugs encontrados y corregidos: TacticalAbsorption no registrado en scenarios, LiquidityExhaustion lista infinita, Absorption sin cooldown. MID_LIQUID LTC: +1.57% Net Taker.
21. **RE-VALIDACIÓN DE ALPHAS — PRÓXIMO 🔴**: Validar edge en todos los clusters (MEGA, MAJOR, MID, THIN, ILLIQUID). Optimizar liquidity_exhaustion y failed_breakout.
22. **OPTIMIZACIÓN DE TIMEOUTS — PRÓXIMO**
23. **LIVE / PAPER TRADING — PENDIENTE**
24. **FIX D1: DETECTORES PER-CLUSTER — COMPLETADO ✅** (2026-06-08): Los 4 detectores ahora resuelven el cluster del símbolo en runtime via `_cluster_cache`. XRP/DOGE reciben THIN_VOLATILE params (z=2.5, noise=0.35). PressureEngine stagnation → porcentual. 10 parámetros conectados. Commit `64a3f2b`.

---

### Current Status: 🟢 Per-Cluster Detector Parametrization (D1 Fix)

- **Architecture**: PressureEngine (centralized CVD/absorption) + 4 AMT scenarios + per-cluster params + SetupEngineV4.
- **Branch**: `8.7-cluster-improved`
- **D1 Fix** (2026-06-08): All 4 detectors now resolve cluster params at runtime via `_cluster_cache`. XRP/DOGE correctly get THIN_VOLATILE params (z=2.5, noise=0.35). PressureEngine stagnation threshold now percentage-based.
- **4 AMT Scenarios**: All registered and firing with per-cluster params. `trend_acceptance` (strongest), `tactical_absorption` (cooldown 120s, structural filter), `liquidity_exhaustion` (sliding window), `failed_breakout` (needs tuning).
- **MID_LIQUID Results** (LTC_TREND_UP_2024-03): 1754 signals, +1.57% Net Taker overall.
- **Next Session**: Re-run THIN_VOLATILE Iter 3 with correct params. Re-run MID_LIQUID orchestration. Validate MEGA_LIQUID thresholds.

---

## 🎯 Plan de Iteración Paramétrica (post-descubrimiento flujo direccional)
...
### Fase 2 — THIN_VOLATILE
> **Parámetros actuales**: z_score_min=1.5, concentration_min=0.40, noise_max=0.35
> **Próximo ajuste**: Implementar Iteración 3 ("El Bisturí") — elevar drásticamente los requerimientos de entrada (z_score_min=3.5, concentration_min=0.75, noise_max=0.20) para rescatar el edge en TAV/LE/FB eliminando el ruido.
...
## 📝 Timeline de Sesiones Recientes
- 2026-06-08 | session-close | **PER-CLUSTER DETECTOR PARAMETRIZATION + STAGNATION FIX**: Audited `analisis_perfil.md` findings. Fixed D1 (all 4 detectors using DEFAULT_PROFILE=MID_LIQUID), PressureEngine stagnation (absolute $0.10 → percentage-based), connected 10 missing params, aligned taxonomy. Commit `64a3f2b`. 7 files, +220 -130 lines.
- 2026-06-06 | session-close | **THIN_VOLATILE Iter 2 Audit & Quality Scorer Bug Fix**: Fixed a critical bug in QualityScorer filtering. Audit of Iter 2 showed a negative Net Taker (-0.3260%), with only `trend_acceptance` as a winner. Established that purely "purging" thresholds isn't enough; need to search for the "golden sliver" of high-conviction signals.
- 2026-06-06 | session-close | **THIN_VOLATILE ITER 1 COMPLETA + PRESSURE ENGINE PER-COIN**: Cancelación de la deuda técnica del PressureEngine. 29 commits, 1466 líneas. Se completó THIN_VOLATILE iter 1 (12 datasets, 4245 señales): DOGE SHORT TAV ratio 1.28, trend_acceptance +0.24% Net. Bug fix: dirección TAV (era reversión), TypeError str/int, TASK_TIMEOUT 1800→3600s, ventana 14400→21600s. Docs: architectural_decisions.md (ADR-1/ADR-2), perfil_changelog.md actualizado. Rama: 8.7-cluster-improved.

- 2026-06-06 | session-close | **THIN_VOLATILE ITER 2 — XRP-ONLY + REGLA DEL EDGE**: Segunda ejecución de THIN_VOLATILE con z=2.5, conc=0.55 produjo 0 trades en XRP — sobrefiltro confirmado. failed_breakout con High Wall (ratio 2.00, +0.39% Net) es el único edge de XRP. Establecida REGLA #5: "Nunca asumas que un edge no existe — sigue ajustando hasta que aparezca". Parámetros movidos a z=1.5, conc=0.40 para próxima iteración.
- 2026-06-03 | session-close | **REGIME SENSOR AUTOPSY + MARKOV DISCUSSION**: Deep analysis of why sensor misclassifies BALANCE as TREND ~60%. Root cause: CB slow drift bypasses synthesis, binary persistence. Markov Chain approach discussed as alternative.
- 2026-06-03 | session-close | **REGIME VALIDATOR + COUNTER-TREND PENALTY**: Created regime_validator.py. Added A-grade minimum for counter-trend signals. -84% false admissions validated.
- 2026-06-02 | session-close | **ILLIQUID_SPEC BACKTEST + PROFILE CONTRADICTION**: Backtest SOL/XRP/DOGE. SOL +0.24% (edge marginal). Profile contradiction discovered — K-Means non-deterministic.
- 2026-06-01 | session-close | **PROFILE SYSTEM V3 — INSTITUTIONAL CLUSTERING**: 4 dimensions, K-Means, silhouette 0.538. Static taxonomy v4.0_FIXED with 14 assets.
- 2026-06-01 | session-close | **PROFILE VALIDATION VOLATIL_BAJO_FLOW — FINAL**: 6 iterations. Winner: iter 3 (+0.0455% Net Taker). AVAX/SUI TAV = ENTRY FAILURE.
- 2026-05-30 | session-close | **POC-BASED DYNAMIC TARGETS**: TP = POC distance. V2 Net Taker +0.8527%. Global +0.6546%. Best historical result.
- 2026-05-30 | session-close | **BEAR GAP FIX**: Macro override, threshold 0.25, confidence 0.85. BEAR_Apr24 L/S 1.31→0.49 🎯.
- 2026-05-28 | session-close | **v8.4 CRYSTAL REFORGE**: Quality Pipeline + Exhaustion Core. 177 signals, 37% WR, Net Taker +0.0012%.
- 2026-05-27 | session-close | **CRYSTAL CLEANUP**: -2,172 lines, 6 files deleted, 8 files pruned. Net Taker +0.1155%.


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
