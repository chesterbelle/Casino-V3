# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> **10. GOTCHA (CORRUPTED GZIP ON INTERRUPT):** Si `build_monthly_datasets.py` o `cryptohftdata_fetcher.py` se interrumpen (disk full, timeout), los `.csv.gz` pueden quedar truncados. Al reanudar, el fetcher los skipea como "already exists". Verificar integridad con `gzip -t` y re-descargar corruptos con `--force`. El script `build_monthly_datasets.py` tenía el bug del glob `????-??-??` que agarraba TODOS los raw files de ese símbolo (incluyendo 2023-2025). SOL no fue afectado porque no tenía raw previos. Ya fixeado con `{month_prefix}-??`.
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DEL EDGE (NUNCA RENDIRSE):** NUNCA concluyas que "el edge no existe" o "ENTRY FAILURE" como veredicto final. Si no encontramos edge, es porque no hemos ajustado los parámetros correctos — seguimos ajustando sensores, targets, regímenes e infraestructura hasta que aparezca. No existen alphas muertas, solo parámetros no encontrados.
> 4. **GOTCHA (CRYPTOHFTDATA SEQUENTIAL):** Para símbolos grandes (ETH, BTC), usar `--sequential` en `cryptohftdata_fetcher.py` para descargar hora por hora en vez de las 24 en paralelo. Sin ello, el proceso muere por OOM (~24-48GB RAM para ETH orderbook). Con sequential, cada hora se descomprime, convierte y escribe al CSV.gz individualmente.
> 5. **GOTCHA (L2_PROCESSOR NAMING):** `l2_processor.py` busca raw files por substring `--name`. El fetcher crea `{exchange}_{type}_{date}_{symbol}` pero el processor espera `{symbol}_{date}`. Renombrar raw files antes de procesar o especificar `--name` con el orden correcto.
> 6. **GOTCHA (TIMEOUTS):** Al ejecutar `scripts/orchestrator.py`, el timeout del shell debe ser muy largo (ej. 4 horas) ya que los backtests masivos toman tiempo considerable.
> 15. **GOTCHA (NOHUP PARA PROCESOS LARGOS):** Nunca correr backtests/audits con `timeout` — al cortar abruptamente deja WAL/SHM huérfanos que cuelgan futuras ejecuciones. En su lugar, usar `nohup` para no bloquear al agente:
>     ```bash
>     nohup python3 scripts/backtest_runner.py --mode audit --symbol LINKUSDT > /tmp/audit_{symbol}.log 2>&1 &
>     ```
>     Luego monitorear con `tail -f /tmp/audit_{symbol}.log`. Para reparar WAL/SHM huérfanos existentes:
>     ```bash
>     python3 -c "conn=sqlite3.connect('dataset.db'); conn.execute('PRAGMA wal_checkpoint(TRUNCATE)'); conn.execute('PRAGMA journal_mode=DELETE'); conn.execute('VACUUM'); conn.close()"
>     ```
> 7. **GIT FLOW (3 BRANCHES):** Ver sección "🏛️ Git Flow Metodología" más abajo.
> 8. **GOTCHA (GIT CLEANUP):** Si ves muchas branches viejas (`git branch | wc -l` > 5), es hora de limpiar. Borra branches locales mergeadas: `git branch --merged main | grep -v "\*" | xargs git branch -D`. Las branches remotas se borran con `git push origin --delete <branch>`.
> 9. **REGLA DE ARQUITECTURA (DOCUMENTACIÓN VIVA):** Si cambias la arquitectura (renombrar clases, mover carpetas, eliminar parámetros), **DEBES actualizar** `docs/ARCHITECTURE_MAP.md` ANTES de hacer commit. Este archivo es la fuente de verdad; si está desactualizado, miente y causa confusión.
> 11. **TERMINOLOGÍA (EVITAR CONFUSIÓN — walk-forward vs validación OOS):** El término "walk-forward" se usó de forma ambigua en sesiones previas. Definiciones correctas:
>     - **Optimización paramétrica** = ajuste de parámetros sobre datasets **diarios (24h)** vía `scripts/cluster_optimizer.py` (Optuna) o `scripts/backtest_runner.py --mode audit/trade`. Aquí se encuentran los golden params.
>     - **Validación OOS mensual** = correr los datasets **mensuales** (`data/datasets/monthly_backtest_ready/AVAX_monthly_2026_0M.db`) SIN reentrenar. Los params se ajustaron en diario, NUNCA en mensual → es out-of-sample real. **Esto es lo que estamos haciendo ahora con AVAX.** (Un walk-forward estricto re-optimiza en cada ventana; nosotros optimizamos una vez en diario y validamos holdout en mensual — por eso el término preciso es "validación OOS mensual", no "walk-forward".)
> 12. **HIPÓTESIS ACTUAL (no confundir con "arreglar AVAX"):** Validar si el **sistema de perfiles** generaliza la estrategia ajustada en LTC a AVAX usando **SOLO parámetros de perfil** (sin cambios de código). El perfil AVAX = copy-paste del perfil LTC + ajustes por moneda. Cualquier cambio de código en los sensores CONTAMINA el test de generalización → PROHIBIDO.
> 13. **REGLA DE NO-CONTAMINACIÓN:** NO ejecutar cambios (código/config/backtest) sin instrucción explícita "sí" del usuario. Investigar/leer es libre. Pasos chicos y reversibles. El branch `dev-9.0-validacion-oos` solo es un nombre git; el método es validación OOS mensual.
> 14. **REGLA GIT MERGE (SANTUARIO MAIN):** NUNCA hagas `git merge` a `main`, `git push origin main`, ni `git push origin --tags` sin autorización explícita "sí" del usuario. La certificación (merge + tag) la decides TÚ, no el agente. El agente solo prepara; tú certificas.
> 16. **GOTCHA (PER-DATASET RESULTS):** El `historian.db` (`data/historian.db`) es el unificado del audit más reciente. Contiene señales de TODOS los datasets en `signals`, cada una con `session_id` único por dataset. Para separar por dataset:
>     1. Identificar sessions: `SELECT session_id, COUNT(*), MIN(timestamp) FROM signals GROUP BY session_id ORDER BY MIN(timestamp)` → cada session_id corresponde a un dataset ordenado por fecha.
>     2. Mapear timestamps a datasets: cada dataset (`DOGEUSDT_TREND_UP_2025-04-01.db`) tiene señales cuyo `MIN(timestamp)` cae en el día del dataset.
>     3. Extraer por session: crear DB temporal filtrando `signals WHERE session_id='...'` + `price_samples` por rango de timestamp, y correr `setup_edge_auditor.py --db <filtered.db>`.
>     Esto evita re-correr backtests. Los `session_id` están en formato `sess_SYMBOL_hash` y se mapean por fecha al dataset correspondiente.
> 17. **REGLA DE ORO (PRE-FLIGHT EXCHANGE ANTES DE CADA RUN):** NUNCA lanzar un run de endurance/paper/demo sin antes verificar que el exchange arranca en CERO posiciones y CERO órdenes. `reset_data.py` solo limpia estado LOCAL — NO toca el exchange. Si queda residuo de una corrida anterior (posición fantasma u órdenes huérfanas), el bot lo reconciliará/adoptará al arrancar (diseño intencional para resiliencia ante crashes) y CONTAMINA los datos de la prueba. Secuencia obligatoria (documentada en `stress-test.md` Paso B.0):
>     ```bash
>     .venv/bin/python utils/emergency_cleanup.py   # limpia exchange a cero
>     # + verificación: 0 posiciones y 0 órdenes (assert en el comando del workflow)
>     .venv/bin/python utils/reset_data.py          # limpia estado local
>     ```
>     Lección 2026-08-03: una posición fantasma del run anterior (PC reiniciado) generó 451 cierres fallidos (~8h de run contaminado con 445 errores -1007, 4 TASK STALL, 2 OCO_ABORT). Fix de símbolo + cooldown no evitan el residuo: la VERIFICACIÓN pre-flight es el único guard.
> 18. **NO MODIFICAR main.py CON HYGIENE CHECK:** El reconcile/adopt de posiciones existentes al arranque es diseño INTENCIONAL (resiliencia: si el bot crashea o falla la luz, al reiniciar adopta lo que hay en el exchange). NO añadir limpieza automática al arranque del bot. La limpieza pre-run es responsabilidad del operador/agente (Regla 17).
> 19. **ARQUITECTURA (TWO-LAYER ORPHAN RECOVERY — Phase 250):** Cuando el OCO Manager tiene un timeout/exception durante el placement de una market order, NO debe asumir el estado del exchange (3 realidades posibles: orden nunca llegó, orden pendiente, orden llenada). El patrón correcto es: **Layer 1 (OCO Manager)** marca `PENDING_VERIFICATION` en tracker + registra entry en tabla `pending_orphan_check`. **Layer 2 (ReconciliationService)** tiene una fase `check_pending_orphans()` con grace period de 5s que consulta el exchange y resuelve: si hay posición → force-close + `ORPHAN_RECOVERY` (healed=True, no contamina error leakage); si no hay → `NOT_FILLED` + `finalize_removal`. Separation of concerns: OCO Manager maneja órdenes, ReconciliationService es la fuente de verdad del exchange.
> 20. **GOTCHA (MULTI-COIN COMMA-JOINED SYMBOL):** `--symbol LTCUSDT,SOLUSDT,AVAXUSDT` se parsea en `main.py` como lista de targets, pero `ExchangeAdapter.symbol` se queda con el string crudo `"LTCUSDT,SOLUSDT,AVAXUSDT"`. Lugares que usan `self.symbol` como fallback (sin argumento explícito) intentarán tratar el string completo como UN solo símbolo → `-1121 Invalid symbol` de Binance. **Solución**: TODA llamada a métodos de connector/adapter en código multi-coin debe pasar una lista explícita, NUNCA `None`. Detección: `if symbol == "MULTI" or (isinstance(symbol, str) and "," in symbol): skip / use list`.
> 21. **GOTCHA (--timeout GRACEFUL SHUTDOWN):** Para runs largos (endurance tests) usar `--timeout N` (en MINUTOS) como argumento de `main.py` — implementa drain phase + `SIGNAL_STOP` graceful. NO usar `timeout` shell command (corta abruptamente, deja WAL/SHM huérfanos). Comando correcto: `nohup .venv/bin/python main.py --symbol LTCUSDT,SOLUSDT,AVAXUSDT --mode demo --close-on-exit --timeout 720 > /tmp/run.log 2>&1 &`. El timeout es interno de main.py, el shell solo provee background.


## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Quality Pipeline + Exhaustion Core + Profile System + **Regime Filter**.
*   **Current Branch**: `dev-9.3-cleanup-and-stress` (rama de trabajo activa — DG-3R completado)
*   **Stable Branch**: `main` (certificada como **v9.2.0-phase1-ready**)
*   **Active Mode**: Multi-Coin with Profile-Based Adaptation
*   **Active Alpha**: **AMT V10 Alpha** (Profile-Optimized + Regime Filter + SBR).
*   **Datasets**: **84 certificados** (2/2/2 × 14) en `data/datasets/daily_backtest_ready/`. +9 mensuales: 6 LTC (Ene–Jun 2026) + 3 SOL (Mar–May 2026) en `data/datasets/monthly_backtest_ready/`.
*   **Two-Layer Orphan Recovery (Phase 250)**: Certificada 2026-08-07 tras DG-3R.


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
*   **Decisión arquitectónica (2026-07-29)**: Se identificó condición de carrera en Croupier (asyncio.gather concurrent). Se implementó el **Internal Event Bus Refactor (Paso 1.2)**. Ejecución validada con éxito mediante el workflow `/validate-all` (Paso 1.3), erradicando las condiciones de carrera y estabilizando la infraestructura.
*   **Slim Exit Engine (v11.0 Pasivo)**: Compresión lineal de brackets de intercambio (modify_tp/modify_sl) al superar el max_hold (21600s), eliminación absoluta de salidas activas de mercado (cero llamadas a `close_position()`) para erradicar el slippage. Throttling inteligente de variaciones menores (<0.01% delta).
*   **Audit Mode**: In-trade lock bypass + no execution
*   **Proximity Analysis**: Muestra qué tan cerca están los targets
*   **Two-Layer Orphan Recovery (Phase 250 — 2026-08-07)**: Decisión arquitectónica tras DG-3 (6 OCO_ABORTs dejaron 6 orphans). Layer 1 (OCO Manager) marca `PENDING_VERIFICATION` + registra pending entry en `pending_orphan_check` table. Layer 2 (ReconciliationService) corre `check_pending_orphans()` cada ciclo con 5s grace period → consulta exchange → `ORPHAN_RECOVERY` (force-close + healed=True) o `NOT_FILLED` (finalize_removal). Separation of concerns: OCO Manager NO asume estado del exchange. Validado en DG-3R Multi-Coin 12h: Orphan Hygiene 100% (vs 0% en DG-3), 0 OCO_ABORTs.
*   **Pre-Entry Notional Validation (Phase 251 — 2026-08-08)**: Fix para defecto -4120 detectado en run v2. Trade 4178299900 (SOL LONG) abrió con notional $15 < min $20; fallback `closePosition=True` falló con `-4120 "order type not supported for this endpoint"`, dejando posición SIN BRACKETS 20 min. **Solución**: En `OrderExecutor.execute_market_order()` — `projected_notional = amount * current_price` vs `adapter.get_min_notional()`, rechaza con `ValidationError` si insuficiente. Skips `reduceOnly`/`closePosition`. Fallback graceful si adapter falla. Commit `29d987e`, 17 tests pasan.

### 4. Capa de Escudo (Risk / Regime) — [CERTIFICADA 🟢]
*   **VA_GATE Regime Filter**: Rolling window 8h evalúa estructura de volumen actual; bloquea mean-reversion en tendencia (integrity ~0.001), permite en rango (integrity > 0.15).
*   **VA_GATE Selective by Setup_Type**: Gate selectivo parametrizado por perfil — bloquea mean-reversion (tactical_absorption, failed_breakout, liquidity_exhaustion) en trending, permite trend-following (trend_acceptance). Config `va_gate` en 9 perfiles, lógica `_apply_va_gate()` en SignalArbitrator.
*   **TA Regime Filter (Interno)**: `_is_regime_favorable()` en `TrendAcceptanceDetector` — bloquea chop (vol_ratio > 1.5), permite clean trends (vol_ratio < 1.3). No bloquea POC migration ni VA expansion en trends direccionales limpios. Thresholds teóricos AMT.

## 🏃 Workflow Estándar y Ejecución

*   **Orquestador de Backtest** (`scripts/backtest_runner.py`):
    Es un wrapper/orquestador que agiliza el flujo de trabajo. Hace el pipeline de `backtest.py` + Paralelización + `utils/setup_edge_auditor.py`.
    *   **Audit Mode** (`--mode audit`): Ejecución paralela de múltiples backtests (diarios), fusiona las bases de datos (historian) y corre el edge auditor. Ideal para validación estadística rápida (ej. las 6 corridas de 24h).
    *   **Trade Mode** (`--mode trade`): Simulación realista, secuencial, un solo backtest de principio a fin. Útil para validación OOS mensual masiva (archivos de 10GB+).
*   **Motor Base de Backtest** (`scripts/backtest.py`):
    Es el simulador crudo individual. Si por alguna razón (debug profundo, perfilado, o un solo archivo) necesitas correr un backtest manual puro sin la orquestación del runner, puedes usar este script directamente pasándole el `.db` específico.
*   **Optimizador** (`scripts/cluster_optimizer.py`): Motor Optuna para ajustar los 49 parámetros del cluster. Soporta iteraciones persistentes (`--resume`).
*   **Bot en Vivo / Paper Trading** (`main.py`): Inicializa el `TradingEngine` real, se conecta por WebSocket y tradea o simula en Binance.

**Workflow de Desarrollo (El Ciclo de Vida del Edge):**
1. **Optimizar**: `python scripts/cluster_optimizer.py --symbol LTCUSDT --iterations 50`
2. **Auditar**: `python scripts/backtest_runner.py --mode audit --symbol LTCUSDT`
3. **Guardar Golden Params**: Registrar los resultados en `config/coin_profiles.py`.
4. **Validar OOS (Out of Sample)**: Correr `backtest_runner.py --mode trade` en datasets mensuales (ej. Enero a Junio).
5. **Certificar**: Si el OOS es positivo y consistente, solicitar permiso para hacer merge a `main` y tagear (ej. `v9.2.0`).

## 📍 Ruta y Progreso (Roadmap)

> **[DOCUMENTO MOVIDO]**
> Todo el progreso del proyecto, fases completadas y tareas pendientes ahora vive EXCLUSIVAMENTE en:
> 👉 `docs/ROADMAP_PRODUCCION.md`
>
> **Por favor, lee ese documento para saber en qué fase estamos y qué sigue.**

### 📍 Ruta Actual (Estado Vivo — 2026-08-08)
| Fase | Paso | Estado |
|------|------|--------|
| 1.1 | Non-Regression Test (9 activos) | ✅ Completado (0 regresiones) |
| 1.2 | Internal Event Bus Refactor | ✅ Completado |
| 1.3 | `/validate-all` (8/8 tests) | ✅ Completado |
| 1.4A | Chaos Test (10min, 9 monedas) | ✅ Completado — Error Trades=0, Integrity=PASS, 634 ops |
| 1.4B.1 | Mini-Endurance (4h, LTCUSDT) | ✅ Completado — 7h reales, Error Recovery=$0 |
| 1.4B.2a | Debug-Gate 12h (LTCUSDT) — 1er run | ✅ Completado — bugs A+B fix (`2a34cf6`), -4120 fix (`ec07d2a`) |
| 1.4B.2b | Debug-Gate 12h (LTCUSDT) — 2do run | ✅ Completado — Sheriff fixes (`4be1102`) |
| **1.4B.3** | **Debug-Gate Multi-Coin 12h (LTC+SOL+AVAX)** | **✅ COMPLETADO — DG-3R 720.6m, Orphan Hygiene 100%, 0 OCO_ABORTs, --timeout graceful** |
| **1.4B.4** | **Full Endurance 24h (Certificación formal)** | **🔄 EN CURSO — Run v2 (PID 15063) activo desde 13:13, ~10h elapsed** |
| 1.4B.5 | Multi-Coin Endurance (48h) | 🔄 Pendiente |
| 1.5 | Análisis Drawdown/Riesgo | 🔄 Pendiente |

**Próximo paso**: Completar Run v2 24h → métricas certificadas → merge a `main` + tag `v9.3.0-multi-coin-certified`.

> **📌 NOTA SOBRE DG-3R (2026-08-07):** Run técnicamente PASS pero con muestra estadística insuficiente (3 trades, 0W/3L). Considerar repetir DG-3 Multi-Coin antes de Full Endurance 24h si se busca validación de edge (no solo de estabilidad). La arquitectura Two-Layer Orphan Recovery está certificada: código NO se disparó en el run (no hubo timeouts), pero está listo. Métrica clave: 722 ciclos de reconciliación sin un solo fallo.

> **🛡️ FIX APLICADO (2026-08-08 — Commit `29d987e`):** Pre-Entry Notional Validation previene -4120 bracket failures. Trade 4178299900 quedó sin brackets 20 min por notional $15 < min $20. Ahora se rechaza en entry.

> **🔁 METODOLOGÍA DEBUG-GATE (decisión 2026-08-03):** La Full Endurance se divide en dos gates para iterar más rápido:
> 1. **Gate de Depuración (12h):** Corre 12h. Si aparece error → fix → repetir. Objetivo: 2 runs consecutivos limpios.
> 2. **Gate de Certificación (24h):** Solo cuando los 2× 12h estén limpios. Este es el criterio formal de certificación del roadmap.
> Esto evita esperar 24h para descubrir errores que se manifiestan en las primeras horas.

## 🏗️ Metodología de Ingeniería Confiable (Fase Producción)

### Plan Maestro (¿Qué hacer?)
El roadmap de producción vive en un solo lugar:
👉 [`docs/ROADMAP_PRODUCCION.md`](file:///home/chesterbelle/Casino-V3/docs/ROADMAP_PRODUCCION.md)

Este documento define las **fases**, **pasos** y **criterios de éxito** para llevar el bot de backtest a producción. Es la fuente de verdad para saber en qué paso estamos y qué sigue.

### Workflows (¿Cómo hacerlo?)
Los protocolos ejecutables viven en `.agent/workflows/`. Cada uno es un paso a paso con comandos exactos y criterios de validación:

| Workflow | Slash Command | Propósito |
|----------|---------------|-----------|
| `validate-all.md` | `/validate-all` | Validación progresiva por capas (math → integración → orquestación → estrés) |
| `stress-test.md` | `/stress-test` | Chaos Test (mecánico) + Endurance Test (Mini 4h → Full 24h → Multi 48h) |
| `sync-docs.md` | `/sync-docs` | Sincronización de la tríada documental al final de sesión |

El roadmap referencia estos workflows en sus pasos. **Los comandos específicos viven en los workflows, no en el roadmap**, para evitar desincronización.

### Tríada Documental (¿Cómo registrar?)

1. **`task.md` (El "Durante")**: Documento efímero (lista de checkboxes) creado en el directorio de artefactos para orquestar los pasos exactos de una prueba en curso. Al terminar el día, su contenido se descarta o consolida.
2. **`changelog.md` (El "Después")**: Registro histórico inmutable. Almacena resúmenes concisos de lo que se logró al finalizar una tarea importante. Todo el registro antiguo está archivado en `.agent/historical_logs/`.
3. **`memory.md` (El "Por qué")**: La Biblia Arquitectónica (este documento). Mantiene las reglas doradas, el estatus global del proyecto y las decisiones técnicas de alto nivel. No contiene ruido diario ni listados de tareas.

### Protocolo de Sesión (El ciclo de vida)

1. **Inicio**: Leer `memory.md` completo → consultar `ROADMAP_PRODUCCION.md` → identificar el paso pendiente.
2. **Ejecución**: Ejecutar el workflow correspondiente al paso → crear `task.md` efímero para trackear progreso.
3. **Cierre**: Registrar resultados en `changelog.md` → actualizar `memory.md` si hubo decisiones arquitectónicas → ejecutar `/sync-docs`.
