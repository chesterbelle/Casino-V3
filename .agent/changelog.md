# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE:**
> 1. **Leer este archivo completo al inicio de cada sesión**. Es la verdad absoluta del proyecto.
> 2. **Actualizar el "Estado Actual" y las "Métricas de Capa"** al final de cada sesión.
> 3. **REGLA DE ORO GIT:** 3 BOTS incompatibles en distintas ramas. NUNCA hacer merge/rebase.
> 4. **REGLA DE PUSH:** Solo tras orden expresa del usuario.

## 📝 Historial de Sesiones

### 2026-05-10: Absorption Pipeline Fix + CAPA 0 L2 Discovery
*   **Descripción**: Diagnóstico por capas del alpha de absorción reveló que `AbsorptionReversalGuardian` (Phase 2) estaba desconectado del pipeline. Se integró y se descubrió hallazgo fundamental: sin datos L2 en backtest, la absorción se infiere en vez de observarse.
*   **Detalle Técnico**:
    *   `decision/setup_engine.py`: Integrado `AbsorptionReversalGuardian` en `SetupEngineV4`. Interceptación de señales `TacticalAbsorptionV2`/`TacticalAbsorption`/`AbsorptionDetector` en `on_signal` → `register_candidate()` + `return`. Agregado `on_candle()` handler para evaluar candidatos pendientes y despachar señales confirmadas. Hereda `TraceBulletMixin` con bordes `PHASE2_INTERCEPT` y `PHASE2_CONFIRMED`.
    *   `utils/setup_edge_auditor.py`: Refactored para usar dynamic windows por setup type y track actual TP/SL distances. `print_report` usa `real_outcome` como métrica primaria.
    *   `utils/analysis/per_condition_audit.py`: Actualizado para dynamic windows y real TP/SL outcomes.
*   **Hallazgos por CAPA**:
    *   **CAPA 1A**: Sensor funciona — detecta absorción correctamente (footprint delta Z-score extremes).
    *   **CAPA 1B**: Confirmation sensors no evaluables — guardian estaba desconectado.
    *   **CAPA 2C**: Rotation/continuation ratio negativo vs random. Solo reversion marginal (+0.17).
    *   **CAPA 3A**: MFE/MAE decae monótonamente. Solo a 30s ratio > 1.0.
    *   **CAPA 3D**: Pendiente — ¿Z-score es el predictor, no la absorción?
    *   **🔴 CAPA 0 (CRÍTICO)**: Sin datos L2 en backtest, el `FootprintRegistry` se reconstruye solo desde trades (L1). Delta se infiere (trades en ask=buying, bid=selling), no se observa. Las órdenes reposantes grandes (el fenómeno de absorción) NO son visibles. La detección es una inferencia estadística, no una observación directa.
*   **Implicación CAPA 0**: Todos los backtests previos de absorción son inválidos — el sensor está "adivinando" absorción en vez de observarla. La prioridad es obtener datos L2 para backtest antes de cualquier evaluación de alpha.
*   **TraceBullet**: Verificado que `GuardianManager` emite `GUARDIAN_REJECT` para contra-tendencia (comportamiento correcto). Señales confirmadas que pasan regime filter se despachan correctamente.
*   **Bug menor**: `SensorV3.emit_signal()` usa `self.__class__.__name__` como `sensor_id` (="AbsorptionDetector"), mientras que el worker path usa `self._name` (="TacticalAbsorptionV2"). Interceptación ahora cubre ambos.

### 2026-05-08: Structural Integrity & Validator Alignment — V3.4c Certification
*   **Descripción**: Certificación de la integridad estructural y matemática del pipeline Casino-V3 (V3.4c) para prepararlo para la re-calibración de la estrategia BEAR. Se alinearon los validadores de las Capas 0-3 con la arquitectura reactiva V4 y se corrigieron fallos críticos de metadatos y mocks.
*   **Detalle Técnico**:
    *   `decision/setup_engine.py`: Implementada la inyección de niveles estructurales (POC/VAH/VAL) desde `ContextRegistry` en `_enrich_metadata`. Esto permite a `ExitEngine` y validadores externos conocer la ubicación del precio relativo al valor.
    *   `croupier/croupier.py`: Movida la inicialización de `DriftAuditor` al inicio de `start()`. Ahora el auditor proactivo corre incluso si el Croupier no tiene un motor reactivo (útil para validadores y modo audit).
    *   `croupier/components/reconciliation_service.py`: Añadido flag `force_balance` a `reconcile_all`. Ahora el balance se sincroniza inmediatamente cuando el `DriftAuditor` detecta una desviación, rompiendo el cooldown de 5 minutos en situaciones críticas.
    *   `utils/validators/test_concurrent_positions.py`: Actualizado a la API V4. Se reemplazó `size` por `amount` y se eliminaron llamadas a métodos obsoletos (`monitor_positions`). Certificada la estabilidad de ejecución paralela de 2+ posiciones con OCO independiente.
    *   `utils/validators/auto_healing_validator.py`: Corregido para operar con intervalos de auditoría agresivos (2s) y sin cooldown de reconciliación para validación rápida de "Self-Healing".
*   **Hallazgos y Errores**:
    *   *Metadata Starvation*: `SetupEngineV4` no estaba recuperando los niveles del registro, lo que causaba que las señales no tuvieran contexto estructural.
    *   *Drift Auditor Silencioso*: El auditor no arrancaba en los tests porque el Croupier abortaba el `start()` si no detectaba un motor (`self.engine`).
    *   *WS Self-Healing Overlap*: Se descubrió que el WebSocket es tan rápido que a menudo sana el balance (via ACCOUNT_UPDATE) antes de que el Auditor REST fallback entre en acción.
*   **Estado de la Suite `@/validate-all` (L0-L3)**:
    *   **L0 (Math)**: ✅ CERTIFICADA.
    *   **L1 (Decision)**: ✅ CERTIFICADA (Metadata enrichment fix).
    *   **L2 (Execution)**: ✅ CERTIFICADA (Concurrent positions stable).
    *   **L3 (Resilience)**: ✅ CERTIFICADA (Drift Auditor forced sync).

### 2026-05-07: Crystal Layer Refinements — VWAP Z-score Fix + IN_VALUE Rotation + Target Architecture
*   **Descripción**: Refinamiento del RegimeGuardian V3 y SetupEngine basado en análisis de la "Crystal Layer" (arquitectura de visibilidad). Se corrigieron 3 bugs conceptuales críticos: (1) confusión footprint Z vs VWAP Z, (2) IN_VALUE forzado a REVERSION con TP=VWAP (estructuralmente imposible ganar), (3) targets de rotation relativos a VWAP en vez de entry price. Se refactorizó SetupEngine en 4 sub-métodos.
*   **Detalle Técnico**:
    *   `decision/guardians/regime_guardian.py`: VWAP Z-score ahora se calcula siempre desde `context_registry.get_vwap_zscore()` (no footprint Z). Metadata emite ambos: `vwap_z_score` y `footprint_z_score`. IN_VALUE → CONTINUATION (rotation) en vez de REVERSION.
    *   `decision/guardians/guardian_manager.py`: `evaluate_all()` ahora retorna 4-tuple `(passed, multiplier, mode, value_position)`. Trace `GUARDIAN_BREAKDOWN` enriquecido con `value_position`, `value_acceptance`, `absorption_detected`, `vwap_z_score`, `footprint_z_score`, y `reason` por guardian.
    *   `decision/setup_engine.py`: Refactorizado en 4 métodos: `_find_tactical_signal()`, `_check_squeeze_guard()`, `_calculate_targets()`, `_evaluate_lta_structural()`. Rotation targets ahora son ATR-relativos al entry price (no VAH/VAL absolutos). Metadata usa `footprint_z_score` en vez de `z_score`.
    *   `players/adaptive.py`: Lee `footprint_z_score` con fallback a `z_score` (legacy).
    *   `sensors/absorption/absorption_detector.py`: Emite `footprint_z_score` junto a `z_score` (legacy).
*   **Hallazgos y Errores**:
    *   *Footprint Z ≠ VWAP Z*: El footprint Z-score mide magnitud de delta (cross-sectional). El VWAP Z-score mide posición de precio relativo a la media. El RegimeGuardian usaba footprint Z para clasificar value_position, lo que era incorrecto. Con footprint Z, casi todas las señales de absorción eran OUT_OF_VALUE (por selección natural: solo se generan con delta extremo). Con VWAP Z correcto, 94.5% son IN_VALUE.
    *   *IN_VALUE REVERSION es estructuralmente imposible*: TP=VWAP está demasiado cerca del entry cuando el precio ya está IN_VALUE. Data: IN_VALUE REVERSION WR=44%, Exp=-0.028%. IN_VALUE ROTATION WR=55.6%, Exp=+0.104%.
    *   *VAH/VAL Targets absolutos fallan en RANGE*: Si LONG a Z=0.5, VAH (+1Z) está solo 0.5σ arriba (TP demasiado cerca) pero VAL (-1Z) está 1.5σ abajo (SL demasiado lejos). R:R 3:1 en contra. Fix: targets ATR-relativos al entry price con VA como mínimo de TP.
    *   *Weak Trend Guard (revertido)*: Intentar degradar TREND con conf<0.5 a BALANCE empeoró el edge (+0.111% → +0.002%). Los falsos trends en RANGE no son el problema; el problema eran los targets.
*   **Métricas Crudas (9 backtests, LTC × Range/Bear/Bull)**:

| Iteración | Signals | Decided | WR | Gross Exp | Net(Taker) | Net(Maker) |
|---|---|---|---|---|---|---|
| V3.3 (footprint Z) | 116 | 68 | 55.9% | +0.120% | +0.001% | +0.040% |
| V3.4a (VWAP Z, IN_VALUE=REVERSION) | 124 | 71 | 50.7% | +0.036% | -0.085% | -0.045% |
| V3.4b (VWAP Z, IN_VALUE=BLOCKED) | 151 | 95 | 48.4% | +0.111% | -0.009% | +0.031% |
| **V3.4c (VWAP Z, rotation + ATR targets)** | **126** | **73** | **56.2%** | **+0.155%** | **+0.035%** | **+0.075%** |

    *   Per-Condition V3.4c:
        *   RANGE: n=31, WR=50%, MFE=0.253%, MAE=0.188%, Ratio=1.34 → FAILED (mejoró de 34.5%)
        *   BEAR: n=58, WR=50%, MFE=0.303%, MAE=0.302%, Ratio=1.00 → FAILED
        *   BULL: n=37, WR=71.4%, MFE=0.494%, MAE=0.220%, Ratio=2.25 → CERTIFIED
    *   Per-Setup V3.4c:
        *   IN_VALUE|rotation: n=81, WR=55.6%, Exp=+0.104%
        *   OUT_OF_VALUE|reversion: n=27, WR=70.4%, Exp=+0.108%
        *   OUT_OF_VALUE|continuation: n=13, WR=53.8%, Exp=+0.049%
*   **Commit**: Pendiente en branch `v7.3.0-total-spectrum-absorption-v3`

### 2026-05-06: RegimeGuardian V3 — Value Position × Value Acceptance
*   **Descripción**: Reemplazo completo del sistema de detección de régimen basado en velocidad por un modelo estructural basado en Auction Market Theory (AMT). El nuevo modelo clasifica el mercado según Posición de Valor (Z-score relativo a VWAP) × Aceptación de Valor (si el mercado acepta o rechaza nuevos precios).
*   **Detalle Técnico**:
    *   `sensors/regime/market_regime.py`: Nuevo `_synthesize()` elimina TRANSITION state, reemplaza confidence por flags estructurales (`value_acceptance`, `absorption_detected`). Fix del micro layer: absorción ahora tiene dirección (opuesta al CVD agresivo), score > 0, y threshold pv_z < 1.0 (antes < 0.5).
    *   `decision/guardians/regime_guardian.py`: RegimeGuardian V3 con matriz de decisión Value Position × Value Acceptance. BALANCE+OUT_OF_VALUE=strong reversion, TREND+ACCEPTING=continuation, counter-trend BLOQUEADO salvo absorción en EXCESS. Elimina bug de "Local Consensus Override" que permitía counter-trend en tendencias fuertes.
    *   `decision/setup_engine.py`: Fix de setup_type hardcodeado — ahora usa trigger metadata para distinguir reversion vs continuation correctamente.
*   **Hallazgos y Errores**:
    *   *Micro Absorption Invisible*: La absorción devolvía score=0.0 y vote=NEUTRAL, haciendo que fuera invisible para el cálculo de régimen. El `_synthesize()` detectaba la flag pero no tenía peso. Fix: dirección opuesta + score proporcional.
    *   *Absorption Threshold Demasiado Estricto*: pv_z < 0.5 requería precio prácticamente congelado. Cambiado a pv_z < 1.0 (precio se mueve menos de lo esperado).
    *   *Absorción Sin Dirección*: La absorción es direccional (buyers absorbed → reversal DOWN, sellers absorbed → reversal UP). El micro layer perdía esta info con vote=NEUTRAL.
    *   *BALANCE IN_VALUE Bug*: El guardian hardcodeaba "(IN_VALUE)" en el reason incluso cuando Z=4.3. Fix: usar value_position real del Z-score.
    *   *Local Consensus Override*: El V2 guardian permitía counter-trend cuando micro/meso eran NEUTRAL, ignorando el macro TREND. Era el bug original que motivó esta sesión.
*   **Métricas Crudas (9 backtests, LTC × Range/Bear/Bull)**:

| Iteración | Signals | Decided | WR | Gross Exp | Net(Maker) | Continuation Exp | Reversion Exp |
|---|---|---|---|---|---|---|---|
| V2 Guardian | 48 | 21 | 52.4% | -0.023% | N/A | — | — |
| V3 (sin micro fix) | 97 | 53 | 47.2% | +0.001% | -0.079% | +0.011% | -0.018% |
| **V3 (con micro fix)** | **116** | **68** | **55.9%** | **+0.120%** | **+0.040%** | **+0.162%** | -0.005% |

    *   Continuation: 86 signals, WR 56.9%, MFE 0.318%, MAE 0.241%, Ratio 1.32 → WATCH
    *   Reversion: 30 signals, WR 52.9%, MFE 0.277%, MAE 0.240%, Ratio 1.15 → INSUFFICIENT
    *   Counter-trend bloqueados: ~250 señales (SHORT en TREND_UP, LONG en TREND_DOWN)
*   **Commit**: `a58895b` en branch `v7.3.0-total-spectrum-absorption-v3`

### 2026-05-03: Execution Unblocking & Exprimidor Profile Validation
*   **Descripción**: Se resolvió un bloqueo crítico en el sistema de ejecución (Sniper Patience Lock) que congelaba el bot después del primer trade. Se validó el flujo completo del perfil de salida EXPRIMIDOR en SOLUSDT, alcanzando 10 trades en 24h.
*   **Detalle Técnico**:
    *   `main.py`: Se inyectó la dependencia faltante `croupier.context_registry = context_registry` para conectar el orquestador con la memoria de contexto.
    *   `croupier/croupier.py`: Se corrigió el chequeo de cierre de posición (`close_position`) filtrando posiciones en estado `OFF_BOARDING` para que liberen efectivamente el candado `IN_TRADE`.
    *   `decision/guardians/statistical_location_guardian.py`: Se redujo el umbral Z-score para maximizar la recolección de señales tácticas y someter al ExitEngine a estrés de alta frecuencia.
*   **Hallazgos y Errores**:
    *   *Sniper Patience Lock Freeze*: Tras un trade, el PositionTracker hacía un Soft-Delete (`OFF_BOARDING`), lo que causaba que `Croupier` nunca enviara el comando de desbloqueo al `ContextRegistry`.
    *   *Shadow SL Performance*: El mecanismo L2 Shadow SL del perfil EXPRIMIDOR cerró prematuramente y con profit ($+0.4574) 2 operaciones, probando ser efectivo como "Winner Catcher".
### 2026-05-03: Performance O(1) & Structural Integrity (The Silicon Eye)
*   **Descripción**: Se resolvió el cuello de botella crítico en el cálculo del VWAP y se blindó el bot contra errores de naming y precisión mediante una nueva capa de metrología.
*   **Detalle Técnico**:
    *   `core/context_registry.py`: Refactorización de VWAP/STD a complejidad **O(1)** mediante sumas acumulativas y deques.
    *   `core/symbol_manager.py`: Creación del **CanonicalSymbolMapper** para unificar alias (ADAUSDT, ADA/USDT, etc).
    *   `core/tick_registry.py`: Evolución a **The Silicon Eye**; motor de inferencia probabilística que deduce el tick real observando el feed de trades.
    *   `decision/setup_engine.py` & `exit_engine.py`: Implementación de targets dinámicos. **TP = VWAP**, **SL = Entry +/- 3.5Z**.
*   **Hallazgos y Errores**:
    *   *Tick Mismatch*: Se descubrió que el bot fallaba en multi-asset porque no reconocía el formato de nombres de la exchange, aplicando un tick de `0.01` por defecto (2% en ADA), lo que rompía el Market Profile.
    *   *Volume Expansion*: La relajación de filtros (Integridad 0.01, Proximidad 0.35%) permitió certificar el Edge en 9 de 10 monedas auditadas.

### 2026-05-02: Reactive Execution Stability & Validate-All Certification
*   **Descripción**: Se alcanzó la estabilidad determinística en el pipeline reactivo eliminando las "posiciones fantasma" y se certificó la "Capa de Hierro" mediante el protocolo `@/validate-all`.
*   **Detalle Técnico**:
    *   `croupier/components/reconciliation_service.py`: Se implementó el bypass del grace period de 120s en `shutdown_mode`, permitiendo limpiezas instantáneas en auditorías.
    *   `croupier/components/reconciliation_service.py`: Se ajustó el conteo de posiciones locales para ignorar las que están en `OFF_BOARDING`, evitando falsas alarmas de desconexión masiva.
    *   `utils/validators/`: Se modernizaron todos los validadores (Layer 0-4) para alinearse con la arquitectura Absorption V1, corrigiendo errores de tipado y argumentos obsoletos.
*   **Hallazgos y Errores**:
    *   *Ghost Persistence*: El periodo de gracia de reconciliación impedía que los tests de multi-símbolo limpiaran el tracker a tiempo. La solución fue vincular la rigurosidad de la reconciliación al estado de `shutdown_mode`.
    *   *Valentino Purge*: Se confirmó la eliminación de Valentino, sustituyéndolo por el "Winner Catcher" (TP Expansion) como mecanismo primario de captura de volatilidad.

## 🏗️ Estado de las Capas de Certificación

### 1. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **Propósito**: Paridad 1:1 Demo vs Backtest, Latencia < 50ms, Integridad Contable.
*   **Hito Actual (v7.1.0)**: Estabilidad Reactiva y Cierre de Posiciones Fantasma validado.
*   **Métrica de Estrés**: Loop Lag: **1.01ms** bajo carga de 2,000 eventos/seg.
*   **Tag de Restauración**: `v7.1.0-reactive-stability-pass`

### 2. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA ✅]
*   **Propósito**: Validación de Edge (Expectancia Bruta > 0.12%), Win Rate, MAE/MFE.
*   **Estatus**: Absorption V1 validado como única estrategia activa.

### 3. Capa de Acero (Resiliencia / Ejecución) — [CERTIFICADA ✅]
*   **Propósito**: Protección de capital, gestión de fees y salidas de emergencia.
*   **Exit Engine (5-Layer Stack)**:
    *   Layer 5: **Catastrophic Stop** (Drawdown > 50%).
    *   Layer 4: **Thesis Invalidation** (Flow + Wall Collapse + Counter-Absorption).
    *   Layer 3: **Winner Catcher** (TP Expansion via modify_tp).
    *   Layer 2: **Shadow Protection** (Trailing - ACTIVE).
    *   Layer 1: **Session Drain** (Salida progresiva al cerrar).

---

## 📘 Manual Técnico (Protocolos y Flags)

### CLI Flags — Propósito Exacto
*   **`--close-on-exit`**: Sweep de cierre al final. Activa **Drain Phase** defensiva si hay timeout.
*   **`--fast-track`**: Bypasea gates estructurales para testeo de infraestructura. Miente al `SetupEngine` para forzar OCOs. **NUNCA en producción**.
*   **`--audit`**: Zero-Interference Mode. Registra señales sin ejecutarlas para validar Edge puro.

### Protocolos de Validación
*   **`/fast-track-parity`**: Verifica paridad mecánica Demo vs Backtest (30 min, LTC).
*   **`/execution-quality-audit`**: Verifica pipeline asíncrono y latencia (15 min, LTC).
*   **`/edge-audit`**: Certificación de Alpha basada en Expectancia Bruta.
*   **`/long-range-edge-audit`**: Validación en condiciones Range/Bear/Bull (9 backtests).

### Reglas de Operación
1.  **Agnosticismo**: Prohibido el ajuste de parámetros por moneda. La lógica debe capturar el edge institucional global.
2.  **No Sintéticos**: Prohibido inyectar señales falsas. Si no hay trades, se investiga el bug orgánico.
3.  **Flytest**: Valida notional y precisión antes de cada sesión. BTC suele fallar por min notional ($100).

## ⚠️ Gotchas Críticos
1.  **Symbol Normalization**: Usar siempre `normalize_symbol()` (BTC/USDT:USDT ≠ BTCUSDT).
2.  **Historian 0 trades**: Si hay ejecución pero no registro, verificar `confirm_close` en PositionTracker.
3.  **Stagnation Profit-Aware**: El exit por estancamiento NUNCA debe cerrar trades ganadores.
4.  **Fill Price Bug**: Limit BUY por encima del mercado debe llenar al mejor precio (comportamiento real).

---

## 🎯 Objetivo de la Sesión Actual
*   **Meta**: V3.4-Crystal validado. Gross +0.155%, Net Maker +0.075%. BULL CERTIFIED.
*   **Estado de Git**: Sin commit aún en `v7.3.0-total-spectrum-absorption-v3`.
*   **Siguiente paso**: (1) Investigar RANGE (WR 50%, Ratio 1.34 — mejoró pero aún FAILED), (2) Investigar BEAR (WR 50%, Ratio 1.00), (3) Commit de V3.4, (4) Contrato de metadata TypedDict (baja prioridad).
