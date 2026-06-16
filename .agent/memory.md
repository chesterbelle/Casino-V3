# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.
> 5. **REGLA DEL EDGE (NUNCA RENDIRSE):** NUNCA concluyas que "el edge no existe" o "ENTRY FAILURE" como veredicto final. Si no encontramos edge, es porque no hemos ajustado los parámetros correctos — seguimos ajustando sensores, targets, regímenes e infraestructura hasta que aparezca. No existen alphas muertas, solo parámetros no encontrados.
> 6. **GOTCHA (CRYPTOHFTDATA SEQUENTIAL):** Para símbolos grandes (ETH, BTC), usar `--sequential` en `cryptohftdata_fetcher.py` para descargar hora por hora en vez de las 24 en paralelo. Sin ello, el proceso muere por OOM (~24-48GB RAM para ETH orderbook). Con sequential, cada hora se descomprime, convierte y escribe al CSV.gz individualmente.
> 7. **GOTCHA (L2_PROCESSOR NAMING):** `l2_processor.py` busca raw files por substring `--name`. El fetcher crea `{exchange}_{type}_{date}_{symbol}` pero el processor espera `{symbol}_{date}`. Renombrar raw files antes de procesar o especificar `--name` con el orden correcto.
> 8. **GOTCHA (TIMEOUTS):** Al ejecutar `scripts/orchestrator.py`, el timeout del shell debe ser muy largo (ej. 4 horas) ya que los backtests masivos toman tiempo considerable.


## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Quality Pipeline + Exhaustion Core + Profile System.
*   **Current Branch**: `8.8-crystal-layer-refactor`
*   **Active Mode**: Multi-Coin with Profile-Based Adaptation
*   **Active Alpha**: **AMT V10 Alpha** (Profile-Optimized).
*   **Datasets**: **84 certificados** (2 TREND_UP, 2 TREND_DOWN, 2 BALANCE × 14 símbolos) en `data/datasets/backtest_ready/`. +6 mensuales LTC/SOL en `data/datasets/monthly_backtest_ready/`.


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

### 1. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA 🟢]
*   **Architecture**: Quality Pipeline + 4 scenarios + exhaustion gate + dynamic targets + profile system
*   **Profiles**: 5 perfiles microestructura — MEGA_LIQUID (ADA, ARB, NEAR), MAJOR_LIQUID (SOL), MID_LIQUID (LTC, AVAX, OP, APT, BNB, LINK), THIN_VOLATILE (XRP, DOGE), ILLIQUID_SPEC (BTC, ETH)
*   **THIN_VOLATILE Certification** (2026-06-09): Net Taker +0.34% (vs -0.59% baseline) en XRP. Edge recuperado mediante optimización bayesiana de 49 parámetros (100 iteraciones).
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
2. **VERIFICAR INTEGRIDAD DE NUEVA ARQUITECTURA (PRESSURE ENGINE) — COMPLETADO ✅**: Los 4 escenarios migrados (`LiquidityExhaustion`, `FailedBreakout`, `TrendAcceptance`, `TacticalAbsorptionV2`) producen señales consistentes.
3. **CROSS-VALIDATION — PENDIENTE**: Validar robustez de parámetros por perfil(MEGA, MAJOR, MID, THIN, ILLIQUID)
4. **FIX D1: DETECTORES PER-CLUSTER — COMPLETADO ✅** (2026-06-08): Los 4 detectores ahora resuelven el cluster del símbolo en runtime via `_cluster_cache`. XRP/DOGE reciben THIN_VOLATILE params (z=2.5, noise=0.35). PressureEngine stagnation → porcentual. 10 parámetros conectados. Commit `64a3f2b`.
5. **CLUSTER OPTIMIZER — COMPLETADO ✅ + EXPANDED** (2026-06-08): `scripts/cluster_optimizer.py` con Optuna, EdgeAuditor, persistent study DB, cross-coin validation, sensitivity analysis. **49 params** across 8 groups (was 18). `--param-groups` flag para selective optimization. Weight auto-normalization. Próximo: ejecutar THIN_VOLATILE.

---

### Current Status: 🟢 84 Datasets Certified (2/2/2 per Symbol)

- **Architecture**: PressureEngine (centralized CVD/absorption) + 4 AMT scenarios + per-cluster params + SetupEngineV4.
- **Branch**: `8.8-crystal-layer-refactor`
- **Cluster Optimizer** (2026-06-08): `scripts/cluster_optimizer.py` — 49 params across 8 groups (absorption, failed_breakout, liquidity_exhaustion, trend_acceptance, targets, quality, guardians, pressure). `--param-groups` for selective optimization. Weight auto-normalization. Optuna TPE + persistent SQLite + `--resume`.
- **EdgeAuditor get_metrics()**: Programmatic API returning net_taker, root_cause, MFE/MAE, best_uniforms. Used by optimizer.
- **Profile Classification Fix**: `_classify_and_set_profile()` checks `clusters_fixed.json` BEFORE runtime classification.
- **4 AMT Scenarios**: All registered and firing with per-cluster params.
- **MID_LIQUID Results** (LTC_TREND_UP_2024-03): 1754 signals, +1.57% Net Taker overall.
- **THIN_VOLATILE Certification** (2026-06-09): Full Bayesian sweep (100 iter). Net Taker +0.34% (XRP) vs -0.59% baseline. Edge recovered.
- **LTC Optuna Optimization** (2026-06-13): 40 trials (10 init + 30 resume). Best Trial 20: score +0.0905. Params aplicados a `config/coin_profiles.py` como nuevo golden.
- **Last Session** (2026-06-15 V2): **8 fixes de auditoría externa implementados**. SortedList duplicate bug fix, CVD sessionized (reset per liquidity window), VA maturity gate (va_integrity < 0.15 blocks signals), L2 spoofing persistence (≥3 snapshots), volume minimum guard in absorption detector, conflict resolution (conviction = priority × score), slim exit pillars (Break-Even, Trailing Stop, Time Decay), confidence scores in FB/LE/TA scenarios. Documentos de análisis externo eliminados. Commit `2da9833`.
- **Next Session**: Backtests multi-coin con 84 datasets certificados para validar no-regresión de los 8 fixes + optimizar parámetros de slim exit pillars por cluster

---


### Fase 2 — THIN_VOLATILE
> **Parámetros actuales**: z_score_min=1.5, concentration_min=0.40, noise_max=0.35
> **Próximo ajuste**: Implementar Iteración 3 ("El Bisturí") — elevar drásticamente los requerimientos de entrada (z_score_min=3.5, concentration_min=0.75, noise_max=0.20) para rescatar el edge en TAV/LE/FB eliminando el ruido.
...
## 📝 Timeline de Sesiones Recientes
- 2026-06-15 | session-close | **8 FIXES FROM EXTERNAL AUDIT**: SortedList bug, CVD sessionized, VA maturity gate, spoofing persistence, volume min guard, conflict resolution (priority×score), slim exit (BE/Trailing/Decay), confidence scores. Commit `2da9833`.
- 2026-06-15 | session-close | **DATASET PIPELINE COMPLETE**: 84 datasets certificados (2/2/2 por símbolo). +6 mensuales LTC/SOL. Análisis de 97 archivos, renombrado 26, descargado 10 nuevos (ETH/BTC con sequential para evitar OOM), podado 39 excedentes. Bugfix: columnas incorrectas en modo secuencial del fetcher (orderbook usaba `id` en vez de `is_snapshot`).
- 2026-06-13 | session-close | **LTC OPTUNA OPTIMIZATION COMPLETE**: 40 trials (10 init + 30 resume). Trial 20 (+0.0905) reemplaza Trial 7 (+0.0667) y golden baseline (-0.1112). Params aplicados como nuevos golden params de LTC. Creado `.agent/golden_params/ltc.md`.
- 2026-06-12 | session-close | **SOLUCIÓN ESTRUCTURAL DISJOINT BOOK (PRESSURE ENGINE BUCKETS)**: La auditoría detectó que en libros delgados como AVAX, bids y asks nunca coinciden en el mismo precio exacto en los L2 snapshots, arrojando `noise=0.0` y `concentration=1.0` artificialmente y anulando los filtros. Se implementó `book_bucket_pct` paramétrico para agrupar dinámicamente precios cercanos (10 bps para AVAX/THIN y 0 bps para SOL). Ajuste de Optuna aplicado con workers dinámicos basados en RAM/Cores con prioridad nice.
- 2026-06-08 | session-close | **CLUSTER OPTIMIZER FULL EXPANSION (18→49 params)**: Deep audit revealed 31 missing params (FB/LE targets, all cooldowns, guardians, pressure, quality thresholds/weights). Expanded to 49 params, 8 groups. Added `--param-groups` flag. Weight auto-normalization. 1 file, ~+120 lines net. Commit pending.
- 2026-06-08 | session-close | **CLUSTER OPTIMIZER + EDGE AUDITOR + PROFILE FIX**: Built `cluster_optimizer.py` (Optuna, persistent DB, cross-coin, sensitivity). Added `EdgeAuditor.get_metrics()`. Fixed profile classification (static JSON before runtime). Fixed quality scorer weight normalization. Added CASINO_FORCE_PROFILE env var. 7 files, +900 lines. Commit pending.
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
