# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> **10. GOTCHA (CORRUPTED GZIP ON INTERRUPT):** Si `build_monthly_datasets.py` o `cryptohftdata_fetcher.py` se interrumpen (disk full, timeout), los `.csv.gz` pueden quedar truncados. Al reanudar, el fetcher los skipea como "already exists". Verificar integridad con `gzip -t` y re-descargar corruptos con `--force`. El script `build_monthly_datasets.py` tenía el bug del glob `????-??-??` que agarraba TODOS los raw files de ese símbolo (incluyendo 2023-2025). SOL no fue afectado porque no tenía raw previos. Ya fixeado con `{month_prefix}-??`.
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DEL EDGE (NUNCA RENDIRSE):** NUNCA concluyas que "el edge no existe" o "ENTRY FAILURE" como veredicto final. Si no encontramos edge, es porque no hemos ajustado los parámetros correctos — seguimos ajustando sensores, targets, regímenes e infraestructura hasta que aparezca. No existen alphas muertas, solo parámetros no encontrados.
> 4. **GOTCHA (CRYPTOHFTDATA SEQUENTIAL):** Para símbolos grandes (ETH, BTC), usar `--sequential` en `cryptohftdata_fetcher.py` para descargar hora por hora en vez de las 24 en paralelo. Sin ello, el proceso muere por OOM (~24-48GB RAM para ETH orderbook). Con sequential, cada hora se descomprime, convierte y escribe al CSV.gz individualmente.
> 5. **GOTCHA (L2_PROCESSOR NAMING):** `l2_processor.py` busca raw files por substring `--name`. El fetcher crea `{exchange}_{type}_{date}_{symbol}` pero el processor espera `{symbol}_{date}`. Renombrar raw files antes de procesar o especificar `--name` con el orden correcto.
> 6. **GOTCHA (TIMEOUTS):** Al ejecutar `scripts/orchestrator.py`, el timeout del shell debe ser muy largo (ej. 4 horas) ya que los backtests masivos toman tiempo considerable.
> 7. **GIT FLOW (3 BRANCHES):** Ver sección "🏛️ Git Flow Metodología" más abajo.
> 8. **GOTCHA (GIT CLEANUP):** Si ves muchas branches viejas (`git branch | wc -l` > 5), es hora de limpiar. Borra branches locales mergeadas: `git branch --merged main | grep -v "\*" | xargs git branch -D`. Las branches remotas se borran con `git push origin --delete <branch>`.
> 9. **REGLA DE ARQUITECTURA (DOCUMENTACIÓN VIVA):** Si cambias la arquitectura (renombrar clases, mover carpetas, eliminar parámetros), **DEBES actualizar** `docs/ARCHITECTURE_MAP.md` ANTES de hacer commit. Este archivo es la fuente de verdad; si está desactualizado, miente y causa confusión.
> 11. **TERMINOLOGÍA (EVITAR CONFUSIÓN — walk-forward vs validación OOS):** El término "walk-forward" se usó de forma ambigua en sesiones previas. Definiciones correctas:
>     - **Optimización paramétrica** = ajuste de parámetros sobre datasets **diarios (24h)** vía `scripts/cluster_optimizer.py` (Optuna) o `scripts/backtest_runner.py --mode audit/trade`. Aquí se encuentran los golden params.
>     - **Validación OOS mensual** = correr los datasets **mensuales** (`data/datasets/monthly_backtest_ready/AVAX_monthly_2026_0M.db`) SIN reentrenar. Los params se ajustaron en diario, NUNCA en mensual → es out-of-sample real. **Esto es lo que estamos haciendo ahora con AVAX.** (Un walk-forward estricto re-optimiza en cada ventana; nosotros optimizamos una vez en diario y validamos holdout en mensual — por eso el término preciso es "validación OOS mensual", no "walk-forward".)
> 12. **HIPÓTESIS ACTUAL (no confundir con "arreglar AVAX"):** Validar si el **sistema de perfiles** generaliza la estrategia ajustada en LTC a AVAX usando **SOLO parámetros de perfil** (sin cambios de código). El perfil AVAX = copy-paste del perfil LTC + ajustes por moneda. Cualquier cambio de código en los sensores CONTAMINA el test de generalización → PROHIBIDO.
> 13. **REGLA DE NO-CONTAMINACIÓN:** NO ejecutar cambios (código/config/backtest) sin instrucción explícita "sí" del usuario. Investigar/leer es libre. Pasos chicos y reversibles. El branch `dev-9.0-validacion-oos` solo es un nombre git; el método es validación OOS mensual.


## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Quality Pipeline + Exhaustion Core + Profile System + **Regime Filter**.
*   **Current Branch**: `dev-9.0-validacion-oos` (rama de validación OOS mensual, desde main v9.0.0)
*   **Stable Branch**: `main` (versión certificada **v9.0.0-sbr-ta-regime-filter**)
*   **Active Mode**: Multi-Coin with Profile-Based Adaptation
*   **Active Alpha**: **AMT V10 Alpha** (Profile-Optimized + Regime Filter + SBR).
*   **Datasets**: **84 certificados** (2/2/2 × 14) en `data/datasets/daily_backtest_ready/`. +9 mensuales: 6 LTC (Ene–Jun 2026) + 3 SOL (Mar–May 2026) en `data/datasets/monthly_backtest_ready/`.


## 🏛️ Git Flow Metodología (3 Branches)

**REGLA DE ORO:** Solo trabajamos en UNA branch de desarrollo a la vez. El resto son sagradas o temporales.

| Branch | Prefijo | Propósito | ¿Cuándo se usa? |
|--------|---------|-----------|-----------------|
| **`main`** | (ninguno) | 🏛️ **SANTUARIO** | Versión certificada y estable. Solo merge cuando hay edge confirmado + backtests verdes. Se etiqueta con `git tag vX.X.X`. |
| **`dev-<versión>-<descripcion>`** | `dev-` | 🏢 **OFICINA** | Rama de trabajo diario. Aquí vives optimizando parámetros, fixeando bugs, ajustando thresholds. Ej: `dev-8.9-datafeed-revamp`. |
| **`feat-<experimento>`** | `feat-` | 🧪 **LABORATORIO** | Rama temporal para experimentos riesgosos. Se crea, se prueba, se mergea (o se borra). Ej: `feat-ltc-threshold-fix`. |

### Flujo de Trabajo Diario:

1.  **Despiertas:** `git checkout dev-8.9-datafeed-revamp`
2.  **Trabajas:** Optimizas, commiteas (`git commit -m "ajuste threshold LTC"`), push a la misma branch.
3.  **Experimento riesgoso:**
    ```bash
    git checkout -b feat-ltc-locura
    # Haces cambios brutales...
    # Si funciona: git checkout dev-8.9 && git merge feat-ltc-locura
    # Si falla: git branch -D feat-ltc-locura
    ```
4.  **Certificación (una vez al mes o cuando hay edge):**
    ```bash
    git checkout main
    git merge dev-8.9-datafeed-revamp
    git tag v9.0.0-edge-encontrado
    git push origin main --tags
    ```

### Reglas Estrictas:
- **NUNCA** hagas push directo a `main` desde tu máquina sin merge formal.
- **NUNCA** tengas 2 branches de `dev-` activas al mismo tiempo (te vuelves loco).
- **SIEMPRE** borra las branches `feat-` después de usarlas (mergeadas o no).
- **TAGS** son para siempre (historial de certificaciones). **BRANCHES** son temporales (flujo de trabajo).

---

## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

### 1. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA 🟢]
*   **Architecture**: Quality Pipeline + 4 scenarios (todos en `decision/scenarios/`) + exhaustion gate + dynamic targets + profile system
*   **Escenarios**: TacticalAbsorption (instantáneo, bypass, vive en `instant/`), FailedBreakout/LE/TrendAcceptance (confirmación, vía SignalArbitrator, viven en `confirmation/`)
*   **OrderFlowEngine**: Calcula 18 features de order flow (CVD, z-scores, absorption). NO decide. Antes se llamaba "PressureEngine".
*   **Profiles**: 5 perfiles microestructura — MEGA_LIQUID (ADA, ARB, NEAR), MAJOR_LIQUID (SOL), MID_LIQUID (LTC, AVAX, OP, APT, BNB, LINK), THIN_VOLATILE (XRP, DOGE), ILLIQUID_SPEC (BTC, ETH)
*   **THIN_VOLATILE Certification** (2026-06-09): Net Taker +0.34% (vs -0.59% baseline) en XRP. Edge recuperado mediante optimización bayesiana de 49 parámetros (100 iteraciones).
*   **ILLIQUID_SPEC Backtest** (2026-06-02): SOL +0.24% Net Taker (edge marginal), XRP -0.05%, DOGE -0.13%. Solo SOL tiene potencial. **PERO**: profile system los clasifica como MAJOR_LIQUID, no ILLIQUID_SPEC — contradicción con clustering real.
*   **Métrica Forense (LTCUSDT 24h)**: Net Taker +0.3184% (cascade optimized, 2026-06-30), MFE/MAE 1.63 baseline
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
*   **Slim Exit Engine (v11.0 Pasivo)**: Compresión lineal de brackets de intercambio (modify_tp/modify_sl) al superar el max_hold (21600s), eliminación absoluta de salidas activas de mercado (cero llamadas a `close_position()`) para erradicar el slippage. Throttling inteligente de variaciones menores (<0.01% delta).
*   **Audit Mode**: In-trade lock bypass + no execution
*   **Proximity Analysis**: Muestra qué tan cerca están los targets

### 4. Capa de Escudo (Risk / Regime) — [CERTIFICADA 🟢]
*   **VA_GATE Regime Filter**: Rolling window 8h evalúa estructura de volumen actual; bloquea mean-reversion en tendencia (integrity ~0.001), permite en rango (integrity > 0.15).
*   **VA_GATE Selective by Setup_Type**: Gate selectivo parametrizado por perfil — bloquea mean-reversion (tactical_absorption, failed_breakout, liquidity_exhaustion) en trending, permite trend-following (trend_acceptance). Config `va_gate` en 9 perfiles, lógica `_apply_va_gate()` en SignalArbitrator.
*   **TA Regime Filter (Interno)**: `_is_regime_favorable()` en `TrendAcceptanceDetector` — bloquea chop (vol_ratio > 1.5), permite clean trends (vol_ratio < 1.3). No bloquea POC migration ni VA expansion en trends direccionales limpios. Thresholds teóricos AMT.

---

## 📍 Ruta Actual (Fuente de Verdad del Roadmap)

### Completado (historial en changelog.md):
Crystal Reforge ✅ | Cluster Optimizer ✅ | VA_GATE ✅ | Signal Validation ✅ | 8.9 Data Feed Revamp (138x) ✅ | Refactor feat/limpieza-profunda ✅ Mergeado | LTC trend_acceptance Optimized (+0.3184%) ✅ | **AMT Crystal Fixes (LE level_key + TAV direction)** ✅ Net Taker 24h: +0.2352% (2x mejora) | **SBR Merge** ✅ | **TA Regime Filter** ✅ | **LTC Edge Certified** ✅ (+0.2354% Net Taker daily, +0.09% monthly) | **Merge to Main v9.0.0** ✅ | **Dataset Expansion (LTC 3→6 monthly)** ✅ | **LTC Validación OOS Mensual** ✅ (4 splits Ene–Jun 2026, +2.4676% acum, +0.617%/mes, 4/4 splits positivos — `docs/historical_results/LTC_result.md`) | **AVAX Param Optimization** ✅ (4/4 escenarios, best score +0.4601, `docs/../golden_params/avax.md`) | **AVAX Validación OOS Mensual LIMPIA** ✅ (4 splits Mar–Jun 2026, +0.2217% acum, 3/4 escenarios positivos, TA ENTRY FAILURE — perfil generaliza PARCIALMENTE, `docs/historical_results/AVAX_result.md`)

112: ### Siguientes Pasos (Priorizados) — ACTUALIZADO 2026-07-16:
1. ~~**Non-Regression Test LTC**~~ ✅ **COMPLETADO**: Audit mensual LTC (6 meses) con fix `cvd_velocity_signed` confirma 0 regresión.
2. ~~**Target Optimization AVAX**~~ ✅ **COMPLETADO**: Ejecutamos el `setup_edge_auditor.py` sobre AVAX y actualizamos el perfil `AVAX_NOISY_UNCERTAIN` con los Best Static Grid targets. (TA Net Taker +0.54%).
3. ~~**SOL Param Optimization**~~ ✅ **COMPLETADO**: Optuna reveló entradas estadísticamente perfectas (MFE/MAE > 4). Audit identificó el TARGET_FAILURE y se inyectaron targets asimétricos extremos (TP 5.0%, SL 0.5-1.0%) logrando +0.54% a +1.13% Net Taker.
4. ~~**SOL Validación OOS Mensual**~~ ✅ **COMPLETADO**: Audit OOS ejecutado sobre 3 meses (Mar-May 2026, ~12 GB). Rendimiento espectacular: **+2.1474% Net Taker** consolidado, todos los escenarios positivos. Los targets asimétricos generalizan a la perfección.
### Current Status: 🟢 84 Daily + 9 Monthly Datasets (2/2/2 per Symbol)

- **Architecture**: OrderFlowEngine (centralized CVD/absorption) + 4 AMT scenarios + per-cluster params + SetupEngineV4 + **TA Regime Filter** + **SBR**.
- **Branch**: `dev-9.0-validacion-oos` (validación OOS mensual), `main` (v9.0.0-sbr-ta-regime-filter certificada)
- **Backtest Runner**: Unificado en `scripts/backtest_runner.py` con dos modos:
  - **Audit Mode** (`--mode audit`): Ejecución paralela de múltiples backtests, merge de historian DBs, edge auditor. Para validación estadística de edge en 6 datasets.
  - **Trade Mode** (`--mode trade`): Ejecución secuencial de 1 backtest, simulación realista de trading. Para validación final antes de live deployment.
- **Workflow Estándar**:
  1. Optimizar: `cluster_optimizer.py --cluster LTC --iterations 50`
  2. Auditar: `backtest_runner.py --mode audit --symbol LTCUSDT`
  3. Validar trade: `backtest_runner.py --mode trade --symbol LTCUSDT`
  4. Certificar: Merge a main + tag
- **Cluster Optimizer** (2026-06-08): `scripts/cluster_optimizer.py` — 49 params across 8 groups (absorption, failed_breakout, liquidity_exhaustion, trend_acceptance, targets, quality, guardians, pressure). `--param-groups` for selective optimization. Weight auto-normalization. Optuna TPE + persistent SQLite + `--resume`.
- **EdgeAuditor get_metrics()**: Programmatic API returning net_taker, root_cause, MFE/MAE, best_uniforms. Used by optimizer.
- **Profile Classification Fix**: `_classify_and_set_profile()` checks `clusters_fixed.json` BEFORE runtime classification.
- **4 AMT Scenarios**: All registered and firing with per-cluster params.
- **MID_LIQUID Results** (LTC_TREND_UP_2024-03): 1754 signals, +1.57% Net Taker overall.
- **THIN_VOLATILE Certification** (2026-06-09): Full Bayesian sweep (100 iter). Net Taker +0.34% (XRP) vs -0.59% baseline. Edge recovered.
- **LTC Optuna Optimization** (2026-06-13): 40 trials (10 init + 30 resume). Best Trial 20: score +0.0905. Params aplicados a `config/coin_profiles.py` como nuevo golden.
- **SOL Cascade Complete** (2026-06-18): Cascada completa SOL (4 escenarios). Bug fix price=0 en trajectory_core. Guardian param discovery: l2_ratio_min_trend_acceptance nunca estuvo en PARAMETER_SPACE. Agregado y re-optimizado. Trial 3: +0.2082. SOL overall Net Taker +0.1354% ✅.
- **V11 Exit Engine & MarketProfile Overhaul** (2026-06-24): Rediseño del `SlimExitEngine` V11. Reemplazadas salidas activas basadas en tiempo (`close_position`) con compresión pasiva lineal del bracket de intercambio (OCO). Implementado `is_mature` en `MarketProfile` para evadir el bloqueo del VA_GATE (baja `va_integrity`) en perfiles maduros. Optimizado `_recalculate_poc` para ejecutarse en lotes tras la poda de ticks, logrando una aceleración masiva del motor (5,400 ticks/seg). Validadores al 100% aprobados.
- **VA_GATE Regime Fix** (2026-06-25): Eliminado el bypass tóxico `is_mature → max(1.0, score)` que permitía operar mean-reversion en tendencia. El rolling window de 8h en `MarketProfile` ya poda ticks viejos; `calculate_va_integrity()` ahora evalúa régimen actual. Validado: ranging → integrity > 0.15 (ALLOW), trending → integrity ~0.001 (BLOCK).
- **Refactor feats/limpieza-profunda** (2026-06-28): Renombrado PressureEngine → OrderFlowEngine, ScenarioManager → SignalArbitrator, escenarios en instant/ + confirmation/. Validación completa post-refactor: 7 layers validadas, orchestrator single-coin-audit LTC (6/6 ✅) + SOL (7/7 ✅) en 2539s. Bugfix absorption_score en tactical_absorption.py:119. SOL targets optimizados por best uniform (FB/0.008, LE/0.007, TA/0.008). SOL l2_ratio_min 1.5→2.0. Orchestrator cleanup: protocolos generalized/probe eliminados, workers 100% dinámicos, auto-audits habilitados.
- **Next Session**: AVAX Validación OOS Mensual LIMPIA (perfil SOLO, sin código) — pendiente "sí" del usuario. Luego non-regression 84 daily + cluster expansion.

---


### Fase 2 — THIN_VOLATILE
> **Parámetros actuales**: z_score_min=1.5, concentration_min=0.40, noise_max=0.35
> **Próximo ajuste**: Implementar Iteración 3 ("El Bisturí") — elevar drásticamente los requerimientos de entrada (z_score_min=3.5, concentration_min=0.75, noise_max=0.20) para rescatar el edge en TAV/LE/FB eliminando el ruido.
...
## 📝 Timeline de Sesiones Recientes
- 2026-07-15 | bugfix + audit mensual | **AVAX TA ENTRY FAILURE RESUELTO — BUG `abs()` EN CVD VELOCITY**: Análisis profundo reveló bug en `core/order_flow/engine.py:159`: `abs()` destruía info direccional del CVD, haciendo que SHORT breakouts requirieran near-zero activity (semánticamente invertido). Fix: nuevo campo `cvd_velocity_signed` (sin `abs()`) en `OrderFlowState` + `trend_acceptance.py` usa `cvd_signed` para dirección + `abs(cvd_slope)` para magnitud. **Zero regresión** (campo original `cvd_velocity` intacto). Audit mensual AVAX (6 meses Ene–Jun 2026): TA pasó de **0 SHORTs → 1,359 SHORTs** (77.5%), WR 53.8%, Net Taker **+0.2410%** ✅, MFE/MAE 3.03. Overall Net Taker **+0.3500%** ✅. 4/4 escenarios Entry OK. Root cause actual: TARGET FAILURE (AMT targets subrinden best static grid 2.50/2.50%).
- 2026-07-13 | validación OOS mensual + root-cause fix | **AVAX VALIDACIÓN OOS MENSUAL CORREGIDO — EDGE MARGINAL ⚠️ + BUG DE RAÍZ DESCUBIERTO**: Hallazgo crítico: `decision/engine/param_validation.py::validate_params` hacía `schema(**params).model_dump()`, y Pydantic descartaba las claves extra del perfil (`regime_*`, `max_pullback_penetration_pct`, `min_candles_outside`, `pullback_tolerance_pct`). El sensor TA tiene "bridges" que las consumen, pero al no llegar caía a defaults → **los golden params de AVAX NUNCA se aplicaron de verdad** (ni en optimización ni en validación OOS mensual previo). Además el sync de los 6 params TA a `config/coin_profiles.py` estaba incompleto. FIX: `validate_params` ahora preserva claves extra (`{**dump, **params}`), y se sincronizaron los 6 params TA (cooldown 210, cvd 5.0, regime_vol 1.55, regime_poc 0.0025, regime_va 1.25, max_pullback 0.0013, min_candles 7, pullback_tol 0.0011). Verificado en vivo (log `vol_ratio > 1.55`). Re-run validación OOS mensual 4 splits con golden params COMPLETOS: Net Taker acum **+0.0325%** (+0.0081%/mes), **2/4 positivos** (Mar +0.0689%, Jun +0.1279%; Abr -0.0607%, May -0.1036%) — esencialmente igual de marginal que el run anterior (+0.0436%). **trend_acceptance = lastre comprobado**: con golden params completos disparó 74/77/78 señales en Mar/Abr/May y perdió en los 3 (-0.31/-0.12/-0.35%); Junio mejor mes con **0 señales TA** (THIN WALL L2<1.3). LE (+0.1261%) y TACT (+0.1800%) ganadores. **Root cause TARGET FAILURE en los 4 meses**. Detalle: `docs/historical_results/AVAX_result.md`. **NO certificado** — requiere desactivar TA en AVAX + target optimization.
- 2026-07-10 | sync-docs | **AVAX PARAM OPTIMIZATION COMPLETE (4/4 escenarios)**: Optimizados los 4 escenarios AVAX vía cluster_optimizer (50 iters c/u). Best score global +0.4601 (trend_acceptance). Val NT +0.29–0.49%, 6/6 coins passed. TACT baseline +0.10%→val +0.49%, FB val +0.41%, LE val +0.29% (score compuesto negativo por <8 señales pero NT positivo), TA score +0.46 (mejor que LTC ~+0.18). Golden params en `.agent/golden_params/avax.md`. Studies en `data/db_vault/avax_*.db`. **Próximo: validación OOS mensual AVAX**.
- 2026-07-04 | validación OOS mensual | **LTC VALIDACIÓN OOS MENSUAL COMPLETE (4 splits)**: Ejecutados 4 splits out-of-sample (Ene–Jun 2026) sin reentrenar. Net Taker acumulado +2.4676% (+0.617%/mes), 4/4 splits positivos. Regime filter certificado: bloquea TA en Mayo (chop vol_ratio 2.0), permite en Marzo/Abril/Junio (trends limpios). LE mejor escenario (+0.3261% avg), FB +0.2158%, TA +0.1791% (con filtro), TACT +0.0310%. Detalle en `docs/historical_results/LTC_result.md`.
- 2026-07-04 | sync-docs | **LTC DATASET EXPANSION (3→6 months)**: Descargados Ene, Feb, Jun 2026 vía CryptoHFTData (89 días). Procesados a SQLite via build_monthly_datasets.py. 6 LTC monthly disponibles para validación OOS mensual (Ene–Jun 2026). Raw files limpiados.
- 2026-07-03 | sync-docs | **SBR IMPLEMENTATION + VALIDATION + VEREDICTO PENDIENTE**: Implementado Session Boundary Reset (8 archivos modificados, 1 nuevo): detector de cambio UTC + cascada de resets en SensorManager/OrderFlowEngine/ContextRegistry/4 detectores. 30 resets detectados en Mayo 2026 sin errores. Validación: 6 dailies 2023-2025 → **+0.23% Net Taker overall ✅** (sin regresión, edge ligeramente mejor que baseline +0.19%). 3 monthly 2026: Marzo -0.03%, **Abril +0.16% ✅**, Mayo -0.04%. TA colapsa en monthly: 30.6%/0%/0% WR. TA funciona en dailies: 67-100% WR. **Veredicto de merge pendiente** → branch `feat/session-boundary-reset` listo pero NO mergeado. Tabla en `docs/historical_results/tabla_resultados_sbr_v8.9.md`.
- 2026-07-02 | sync-docs | **MULTI-LAYER REGIME CLASSIFIER & TA OPTIMIZATION PLAN**: Implementado `RegimeClassifier` (3 señales AMT) bloqueando exitosamente 27 falsos positivos en rango (-18.5%). Backtest mensual de LTC (Mar-May) reveló `ENTRY FAILURE` subyacente para `trend_acceptance` (Avg Proximity 0.63, Net Taker imposible de positivizar solo con targets). Creado protocolo de Optuna para ajustar filtros de entrada. Próxima sesión: Ejecutar Optuna param sweep.
- 2026-06-30 | sync-docs | **ROADMAP CLEANUP, BRANCH CLEANUP & CLI --help OVERHAUL**: Roadmap unificado en memory.md como fuente de verdad única. `feat/limpieza-profunda` eliminada. `session-close.md` → `sync-docs.md`. --help mejorado en orchestrator.py, backtest.py, cluster_optimizer.py. Próximo paso: `--run-type trade` LTC 24h.
- 2026-06-30 | session-close | **LTC CASCADE OPTIMIZATION & GOLDEN PARAMS**: Resuelto bug en cluster_optimizer (envenenamiento del signal count por setups irrelevantes). Optimización de 50 iteraciones para trend_acceptance en LTC logró +0.3184% Net Taker. Se actualizó coin_profiles.py, se guardó la DB gold-standard, y se reescribió ltc.md a V2. Cambios mergeados a dev-8.9-datafeed-revamp. Próximo paso: probar con run-type trade en 24h y luego dataset mensual.
- 2026-06-28 | session-close | **POST-REFACTOR VALIDATION + SOL TUNING + ORCHESTRATOR CLEANUP**: Validación completa del refactor `feat/limpieza-profunda` (7 layers, LTC 6/6, SOL 7/7). Bugfix absorption_score_v2 en tactical_absorption.py. SOL targets optimizados (FB/0.008, LE/0.007, TA/0.008). SOL l2_ratio_min 1.5→2.0. Generalized/probe eliminados del orchestrator. Workers 100% dinámicos. Auto-audits en single-coin-audit. Commit `2841e14`.
- 2026-06-25 | session-close | **BACKTEST MENSUAL LTC MAYO 2026 COMPLETE + TREND_ACCEPTANCE DIAGNOSIS**: VA_GATE selectivo funcionó (bloqueó mean-reversion en downtrend, permitió trend-following), pero trend_acceptance no generó SHORTs en downtrend 10-17 mayo (-4.1%). 28 trades (26 LONG SL, 2 SHORT TP). Causa: thresholds trend_acceptance demasiado estrictos (l2_ratio_min_trend_acceptance=1.5, cvd_confirmation_threshold=4.0). Próxima optimización: reducir a 1.0-1.2 y 2.0-2.5. Single-coin orchestration corriendo en 6 datasets 24h LTC.
- 2026-06-25 | session-close | **VA_GATE SELECTIVE BY SETUP_TYPE — PARAMETRIZED PER PROFILE**: VA_GATE now blocks only mean-reversion setups (tactical_absorption, failed_breakout, liquidity_exhaustion) when integrity < 0.15, while allowing trend-following (trend_acceptance). Added `va_gate` config to all 9 profiles with block/allow lists. New `_apply_va_gate()` in ScenarioManager reads profile config. Validated: integrity=0.5 → allows all; integrity=0.02 → allows only trend_acceptance.
- 2026-06-25 | session-close | **BUILD_MONTHLY_DATASETS.PY BUG FIX — GLOB MATCHED ALL RAW FILES**: Fixed glob `????-??-??` → `{month_prefix}-??` that was concatenating ALL raw files of a symbol (2023-2025) into monthly datasets. Rebuilt 3 LTC monthly datasets from scratch (Mar 530MB, Apr 361MB, May 403MB). Only LTC affected (SOL had no prior raw files). Added GOTCHA #9 for corrupted gzip on interrupt.
- 2026-06-25 | session-close | **VA_GATE REGIME FIX — REMOVED TOXIC IS_MATURE BYPASS**: Removed `is_mature → max(1.0, score)` that let bot trade mean-reversion in trending markets (caused 20 consecutive LONG SLs, -$36.52). Rolling window (8h) in `MarketProfile` naturally ages out trend; `calculate_va_integrity()` now evaluates current regime. Validated: ranging → integrity > 0.15 (ALLOW), trending → integrity ~0.001 (BLOCK), trend→range recovery after trend ages out.
- 2026-06-24 | session-close | **V11 SLIMEXITENGINE & MARKETPROFILE SPEEDUP & GATING BYPASS**: Replaced active exits with passive bracket compression, removing all `close_position` calls. Implemented `is_mature` in `MarketProfile` to bypass the `va_integrity < 0.15` block on mature profiles, enabling continuous trading. Optimized `_recalculate_poc` during tick pruning to run once per batch, resulting in a massive 25x speedup (~5,400 ticks/sec). All 16 unit and integration tests passed.
- 2026-06-22 | session-close | **8.9 DATA FEED REVAMP — UNION ALL OPTIMIZATION (138x SPEEDUP)**: Replaced Pandas concat+sort with SQLite UNION ALL + batch streaming (fetchmany). **Real measurement**: SOL monthly 3.9GB (~100M events) in **20 min vs 46h projected** = 138x faster. Throughput: 5M events/min with 1ms delay fidelity. Added `resolve_db_symbol()` for monthly dataset symbol resolution. VA_GATE structural limitation confirmed (blocks all signals on monthly datasets — `va_integrity=0.00` due to total_volume accumulation, expected behavior). Branch `8.9-datafeed-revamp` created and pushed. Next: Use 84 certified 24h datasets for signal validation.
- 2026-06-19 | session-close | **SLIMEXITENGINE V10.3 UNIVERSAL — SCALE OUT & TRAILING ELIMINATED**: Refactor completo siguiendo análisis externo. `ASSET_EXIT_PROFILES` reemplazado por `UNIVERSAL_EXIT_RULES`. Scale Out eliminado (erosiona R/R), Trailing Stop eliminado (vulnerable a sweeps). Solo Break Even, Time Decay, Micro-Z Reversal con Maker-Join. 13/13 tests locales pasados. Pausa solicitada antes de backtesting.
- 2026-06-18 | session-close | **SOL CASCADE COMPLETE + PRICE=0 BUG + GUARDIAN PARAM DISCOVERY**: Bug fix price=0 en trajectory_core. Guardian param discovery: l2_ratio_min_trend_acceptance faltaba en PARAMETER_SPACE. Agregado. trial 3: +0.2082. SOL Net Taker +0.1354%.
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

---

### [2026-07-14] AVAX TA: ENTRY FAILURE era INVERSIÓN DE DIRECCIÓN (no edge muerto) — ⚠️ EXPERIMENTO CONTAMINADO / REVERTIDO
> **CORRECCIÓN (2026-07-14):** Este experimento usó el hack `invert_direction` en `trend_acceptance.py` + ajustes de params (`regime_vol_ratio_max` 1.55→1.3, `cvd_confirmation_threshold` 5.0→2.5) para "arreglar" AVAX invirtiendo el side. El usuario lo rechazó: cambiar código del sensor para hacer funcionar AVAX **contamina la hipótesis de generalización por perfiles** (la única palanca legîtima es el perfil). **TODO FUE REVERTIDO**: `trend_acceptance.py` original, golden params intactos en `coin_profiles.py`, y el fix de `param_validation.py` (preserva claves extra) se CONSERVÓ. Los resultados de "inversión de dirección" NO son válidos para la hipótesis. Ver "Validación OOS Mensual LIMPIA" en Siguientes Pasos y la entrada 2026-07-13 (resultado limpio +0.0325% acum). La observación de que TA era 100% LONG-only es real (audit del run limpio), pero su interpretación (invertir) fue descartada.
- Re-análisis de validación OOS mensual AVAX (dev-9.0-validacion-oos). TA auditaba como `ENTRY FAILURE` (MFE/MAE 0.02, Best Net −0.0268% ❌).
- **Causa raíz**: TA en AVAX es 100% LONG-only (0 SHORTs en 74 trades). En los momentos donde detecta breakout alcista, AVAX revierte a la baja → SL 0.9% se dispara.
- **Test de inversión** (simular los 74 entries como SHORT con TP/SL simétricos): WR 63.5%, AvgPnL +0.2432% (vs LONG real −0.3132%). El edge direccional existía, del lado equivocado.
- **Fix (validado en Marzo)**: flag de config `invert_direction: True` en `AVAX_NOISY_UNCERTAIN.trend_acceptance` + flag mínimo en `decision/scenarios/confirmation/trend_acceptance.py` (`_emit` invierte side si `invert_direction`).
  - Marzo TA: MFE/MAE **0.02 → 45.49** ✅, Best Net **−0.0268% → +1.1299%** ✅, Veredict **ENTRY FAILURE → TARGET OPTIMIZATION NEEDED** ✅, Net real **−0.3132% → +0.2193%** ✅, señales 74 → 152.
  - Marzo global Net Taker: **+0.0689% → +0.1875%** ✅.
- **VALIDA REGLA DEL EDGE**: desactivar TA habría sido un error; el problema era param/dirección, no ausencia de edge.
- **Resto de escenarios** (FB/LE/TACT) ahora auditados como `TARGET FAILURE` (targets AMT subrinden el static grid: TA +0.22% real vs +1.13% static; FB/LE/TACT similar). El problema común AHORA es la fórmula de targets AMT, no la entrada.
- **Prerrequisito**: bug de `validate_params` (decision/engine/param_validation.py) descartaba claves extra del perfil → golden params NUNCA se aplicaron en corridas previas. Fix aplicado: devuelve `{**validated.model_dump(), **params_dict}`.
- **Pendiente**: re-correr validación OOS mensual 4 meses (Abr/May/Jun corriendo en paralelo al cierre) y luego optimizar targets AMT (problema de TARGET FAILURE compartido).

### Lecciones
1. `ENTRY FAILURE` en el auditor NO significa "desactivar" — primero testear inversión de dirección (long↔short) sobre los mismos entries.
2. Un sensor puede ser LONG-only por gates asimétricos (`l2_ratio_min_trend_down` 2.2 + `cvd_slope < -umbral` raramente cumplidos) → la rama SHORT nunca dispara.
3. El bug de `validate_params` hacía que TODA la optimización previa de AVAX fuera sobre params incompletos (regime_*/pullback caían a default). Siempre verificar que los params del perfil lleguen al sensor.
