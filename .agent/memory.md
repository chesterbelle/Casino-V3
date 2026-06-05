# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

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
*   **Profiles**: 5 perfiles microestructura — MEGA_LIQUID (BTC, ETH), MAJOR_LIQUID (SOL, BNB, XRP), MID_LIQUID (LTC, ADA, LINK, DOGE — iter 3 validated), THIN_VOLATILE (AVAX, SUI, NEAR, APT, OP, ARB — TAV/FB disabled), ILLIQUID_SPEC (long-tail, disabled)
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

---

### Current Status: 🟢 PressureEngine — 4 AMT Scenarios Activated (MID_LIQUID)

- **Architecture**: PressureEngine (centralized CVD/absorption) + 4 AMT scenarios (trend_acceptance, tactical_absorption, liquidity_exhaustion, failed_breakout) + per-profile params + SetupEngineV4.
- **Branch**: `8.7-cluster-improved`
- **PressureEngine**: Centralized CVD velocity Z-score normalization + absorption detection. Updated per-tick from SensorManager.
- **4 AMT Scenarios**: All registered and firing. `trend_acceptance` (strongest), `tactical_absorption` (cooldown 120s, structural filter), `liquidity_exhaustion` (sliding window), `failed_breakout` (needs tuning).
- **MID_LIQUID Results** (LTC_TREND_UP_2024-03): 1754 signals, +1.57% Net Taker overall. trend_acceptance +1.68%, tactical_absorption +0.12%, liquidity_exhaustion -0.56%, failed_breakout -1.32%.
- **Next Session**: Run full MID_LIQUID orchestration (12 datasets). Optimize liquidity_exhaustion/failed_breakout params. Move to THIN_VOLATILE cluster.

---

## ⚠️ Gotchas Críticos
10. **Taker-Only Execution Mandate**: Toda validación se juzga descontando fees Taker del 0.12%.
11. **Historian Cumulative Runs**: Usar `--historian-db` para aislar archivos SQLite por run.
12. **Parallel Audit SQLite Write Locks**: Usar archivos temporales y consolidar al final.
13. **Break-Even Cost Fallacy**: El Break-Even estático mata el Edge (93.75% winners perdidos). Todo SL debe ser estructural.
14. **TREND_DOWN LONG Tóxico**: LONGS en TREND_DOWN tienen 6% WR (5 TP vs 79 SL). Deberían prohibirse explícitamente. SHORTS en TREND_DOWN: 92% WR.
15. **No es Reversion Clásica**: 0/927 señales V2 revierten en <15 min. Es flujo direccional que se extiende por horas (mediana time-to-TP = 110 min). El nombre "TacticalAbsorptionV2" probablemente está mal.
16. **Timeout Rate ~60%**: Es el drag principal del sistema. Cada timeout cuesta −0.12% fee. Optimizar targets es la prioridad #1.
17. **skip_clean Bug (Orquestador)**: `clean_temp_data()` borra `historian.db*` al inicio de cada protocolo. Si se encadenan protocolos sin `skip_clean=True`, el DB mergeado previo se destruye. Fix: `set_a_avax` y `set_a_sui` tienen `skip_clean=True` — solo borran temporales.
18. **DEFAULT_PROFILE = MID_LIQUID Bug**: `match_profile` y `find_closest_profile` saltaban MID_LIQUID porque `if profile_name == DEFAULT_PROFILE: continue`. Cualquier perfil que fuera DEFAULT no se podía matchear. Removido el skip — ahora DEFAULT_PROFILE es solo un fallback label, no afecta matching.
19. **K-Means No-Determinista**: Cada corrida de `cluster_builder.py --exchange` produce clusters diferentes. Los nombres (MEGA_LIQUID, etc.) son fijos pero los miembros cambian. SOL puede estar en THIN_VOLATILE en una corrida y en MAJOR_LIQUID en otra.
20. **Profile vs Clustering Contradiction**: `profile_diagnostic.py` clasifica SOL/XRP/DOGE como MAJOR_LIQUID, pero `cluster_builder.py` reciente los pone en THIN/MID. El profile system fue calibrado con una corrida previa que ya no es válida.
21. **price_samples sin columna volume**: El historian.db del backtest no tiene `volume` en `price_samples`. `profile_diagnostic.py` fue parcheado para usar fallback estimation.
22. **TacticalAbsorptionV2 no registrado en scenarios**: Hasta 2026-06-05, `TacticalAbsorptionV2` nunca se registró en `self.scenarios` de SensorManager. Solo existía como archivo. Fix: agregado import + registro en `core/sensor_manager.py:112`.
23. **LiquidityExhaustion sliding window bug**: La lista `level_tests` crecía infinitamente. La condición `all(tests[i].delta < tests[i-1].delta * threshold ...)` requería que TODOS los pares fueran decrecientes → imposible con 100+ tests. Fix: poda temporal + revisar solo últimos N.
24. **AbsorptionDetector sin cooldown**: Disparaba 6660 señales/LTC porque no tenía cooldown ni filtro estructural. Fix: cooldown 120s, filtro VA (±0.3%), min Z-score 0.5.

---

## 📝 Timeline de Sesiones Recientes
- 2026-06-04 | session-close | **REGIME SENSOR V2 — PRICE ACTION + VOLUME PROFILE + MARKOV**: Complete redesign from 3-layer to 2-layer architecture. Accuracy 41.3% → **72.3%** (+31pp). TREND_UP 42.2% → **78.0%**. BALANCE 16% → **60%**. Key breakthrough: relaxed swing detection (ANY vs BOTH). Both layers contribute 98%+. Markov trained on 125,280 candles. Commits: e9dfd80, 080e465, 09cc9d5. Branch: 8.7-cluster-improved.
- 2026-06-05 | session-close | **4 AMT SCENARIOS ACTIVATED — ABSORPTION + LIQUIDITY EXHAUSTION FIXES**: Registered TacticalAbsorptionV2 in SensorManager. Rewrote AbsorptionDetector with cooldown+structural filter. Rewrote LiquidityExhaustionDetector with sliding window. Cleaned debug logs. PressureEngine architecture operational. MID_LIQUID LTC: 1754 signals, +1.57% Net Taker. 3/4 datasets positive. Commit: ff3338b.
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
