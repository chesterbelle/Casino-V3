# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Dual-Core (Reversión/Continuación) con Inercia de Micro-Flujo.
*   **Current Branch**: `v8.0.0-absorption-amt`
*   **Active Mode**: Multi-Coin Agnostic (LTC, SOL, BTC Certified).
*   **Active Alpha**: **AMT V10 Alpha** (Certified Generalized).


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos, análisis de fallos (root cause) y la evolución cronológica de las fases (Phase 1200, 2300, etc.).
*   **Uso**: Consultar cuando se necesite profundizar en el "por qué" de una decisión arquitectónica o recuperar datos comparativos que no estén en la Brújula.


---

## 🏛️ Estado de las Capas de Certificación

### 1. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **Propósito**: Paridad 1:1, Resiliencia del Historian, Latencia < 50ms, Integridad Contable.
*   **Hito Actual (v7.3.0)**: **Arquitectura Dual-Core (Reversión/Continuación)**.
*   **Componentes**: `GuardianClassifier` (V3) + `DynamicTargetEngine`.
*   **Métrica de Estrés**: Procesamiento VWAP/STD en **O(1)**. Zero-bottleneck en backtest.
*   **HFT Latency Telemetry (T0-T4)**:
    *   `t0`: Tick exchange | `t1`: Decision | `t2`: Submit | `t3`: Fill confirm | `t4`: PositionTracker.
    *   *Resilient Logic*: Fallbacks en `historian.py` y `position_tracker.py` para evitar NULLs y Silent Skips.

### 2. Capa de Cristal (Estrategia / Alpha) — [WATCH (Alpha Rescue) 🔄]
*   **Propósito**: Validación de Edge (Expectancia Bruta > 0.12%), Win Rate, MAE/MFE.
*   **Hito Actual (v10.1.0)**: **AMT V10 Alpha (Symmetric Variance-Aware)**.
*   **Métricas de Sesión (LTC 24h - 1800s)**:
    *   **Win Rate (Provisional)**: **63.2%**.
    *   **Expectancia Bruta**: **+0.1185%**.
    *   **Targets**: Simetría **1:1** (0.45% TP / 0.45% SL).
    *   **Orchestration**: Alpha Fusion (Composite Signals) operacional y trazable.
*   **Arquitectura**: Escenarios AMT con targets simétricos anclados a ATR con Noise Floor (0.45%).
*   **Exhaustion Gate**: Integrado a nivel detector para bloqueo de "Toxic Surges".

### Sesión 3: Rescate del Alpha y Rediseño "Slim" (V10.2)
*   **Fecha**: 2026-05-13
*   **Objetivo**: Certificar AMT V10 y resolver asfixia de edge.
*   **Resultados**:
    *   **Alpha Rescue**: Recuperado Win Rate del **63.2%** en LTC mediante targets simétricos (1:1 RR) con 0.45% Noise Floor.
    *   **Design Decision**: Condenado el motor de salida de 5 capas por lentitud y complejidad. Aprobado el **Slim Exit Engine (V10.2)**.
    *   **Arquitectura de Perfiles**: Implementación de perfiles por activo (`BLUE_CHIP`, `LIQUID_ALT`, `HIGH_BETA`) para ajustar la agresividad de salida según la personalidad del mercado.
    *   **Ejecución Pro**: Todas las salidas tácticas (Scale Out, BE, Trailing) serán **Maker (Limit Orders)** para eliminar slippage.
*   **Commit**: `slim-exit-blueprint-v10`

### 3. Capa de Acero (Resiliencia / Ejecución) — [CERTIFICADA ✅]
*   **Propósito**: PortfolioGuard, Limit Sniper, ExitEngine stacks.
*   **Resiliencia Validada**:
    *   **Concurrency Guard**: Lock de símbolos (`_inflight_symbols`) para prevenir race conditions en ráfagas de señales de milisegundos.
    *   **Chaos Matching**: 100% de integridad en eventos WebSocket bajo carga masiva.
    *   **Auto-Healing**: Recuperación automática de drifts de balance y "Adoptión" de posiciones huérfanas.
    *   **Lifecycle Awareness**: Ruteo unificado de IDs para cierre de posiciones mediante callbacks simétricos.

---

## 📉 Roadmap: CAPA 0 → Absorption Alpha Validation
1.  **CAPA 0 (Data/Math) — COMPLETADO ✅**: Pipeline L2 operativo.
2.  **REESTRUCTURACIÓN AMT V10 — COMPLETADO ✅**: Arquitectura basada en escenarios AMT.
3.  **VALIDACIÓN ALPHA V10 — COMPLETADO ✅**: Certificada con Audit 4.
4.  **ESTABILIZACIÓN DE EJECUCIÓN — COMPLETADO ✅**: Slim Exit Engine sincronizado y certificado (66% WR).
5.  **CAPA 5 (Risk/Portfolio) — PRÓXIMO PASO**: Gestión de exposición multi-moneda.

---

## 🏛️ Estado de las Capas de Certificación (v10.2.0)
1. **Capa 0 (Data/Math)**: **CERTIFICADA ✅**
2. **Capa 1 (Decision)**: **CERTIFICADA ✅**
3. **Capa 2 (Execution)**: **CERTIFICADA ✅**
4. **Capa 3 (Resilience)**: **CERTIFICADA ✅**
5. **Capa 4 (Strategy)**: **CERTIFICADA ✅** — Slim Exit Engine (V10.2) estable con ruteo de IDs corregido.
6. **Capa 5 (Risk)**: **PENDIENTE 🛡️** — Gestión de riesgos transversales y drawdown limits.

### Sesión 4: Estabilización de Ejecución y Concurrencia
*   **Fecha**: 2026-05-14
*   **Objetivo**: Resolver "Trade Flooding" y ciclo de vida de posiciones en backtest.
*   **Resultados**:
    *   **Recuperación de Escala**: De 1 trade bloqueado a **15 trades fluidos** (PF 1.70).
    *   **Inflight Fix**: Eliminado el sobre-trading duplicado mediante bloqueo por símbolo.
    *   **Unified Routing**: Sincronización exitosa de fills de TP/SL con el `PositionTracker`.
*   **Próximo Objetivo**: Auditoría Generalizada (10 Monedas × 24h) para estresar el motor multi-asset.
*   **Commit**: `d612546`

---

## 🗺️ Mapa de Arquitectura

### Componentes Core
*   `SetupEngine`: Pipeline 4 pasos: `_find_tactical_signal()` → `_check_squeeze_guard()` → guardians → `_calculate_targets()`. Targets por value_position: rotation (ATR-relativo), continuation (1.5*ATR extension), reversion (VWAP target).
*   `RegimeGuardian V3`: Value Position × Value Acceptance. VWAP Z-score clasifica IN_VALUE/OUT_OF_VALUE/EXCESS. IN_VALUE → rotation, OUT_OF_VALUE → reversion/continuation. Absorción = REJECTING. Counter-trend bloqueado salvo absorción en EXCESS.
*   `GuardianManager`: `evaluate_all()` retorna 4-tuple (passed, multiplier, mode, value_position). Trace GUARDIAN_BREAKDOWN enriquecido con regime context.
*   `AdaptivePlayer`: Decisión estratégica (Kelly sizing, TP/SL validation).
*   `OrderManager`: Ejecución de órdenes y recalibración de TP < 50ms.
*   `Croupier`: Orquestador de ejecución y ciclo de vida de posición.
*   `PositionTracker`: Fuente única de verdad de posiciones abiertas.
*   `FootprintRegistry`: Singleton para tracking de Bid/Ask volume y CVD.

### Caja de Herramientas (Toolbox)
*   **Descarga de Datos**: `utils/data/tardis_fetcher.py` (Nuevo estándar de alta fidelidad).
*   **Procesador L2**: `utils/data/l2_processor.py` (Reconstrucción determinista de Orderbook).
*   **Data Reset**: `utils/reset_data.py` (Limpieza de `historian.db` y estados operativos).
*   **Auditoría de Edge**: `utils/setup_edge_auditor.py` (Métricas: Gross Expectancy%).
*   **Análisis de Regímenes**: `utils/analysis/per_condition_audit.py`.

---

## 📘 Manual Técnico (Referencia Rápida)

### CLI Flags — Propósito Exacto
*   **`--close-on-exit`**: Sweep de cierre y Drain Phase defensiva.
*   **`--fast-track`**: [DEPRECADO ⚠️] — Sustituido por el protocolo **TraceBullet**. Ya no se requiere para testear infraestructura, ya que la telemetría TRB permite ver señales rechazadas sin forzar OCOs.
*   **`--audit`**: Zero-Interference Mode. Registra señales sin ejecutarlas.

### Protocolos de Validación (Workflows)
*   **`/fast-track-parity`**: Paridad mecánica (30 min, LTC).
*   **`/execution-quality-audit`**: Pipeline asíncrono y latencia (15 min, LTC).
*   **`/edge-audit`**: Certificación de Alpha basada en Expectancia Bruta.
*   **`@/validate-all`**: Suite completa de 6 capas (Math -> Stress -> Chaos).

### Protocolo de Debugueo: TraceBullet 🎯
*   **Propósito**: Seguimiento determinístico de eventos en sistemas asíncronos y multiversionados.
*   **Implementación**: `TraceBulletMixin` inyecta telemetría en `metadata["trace_id"]`.
*   *Uso*: Activar con `TRACE_BULLET_ACTIVE=1` para capturar la trayectoria exacta de una señal a través de los componentes.
*   *Bordes Críticos*: `SENSOR_INGEST` -> `PHASE2_INTERCEPT` -> `GUARDIAN_CHECK` -> `PHASE2_CONFIRMED` -> `SETUP_GEN` -> `EXEC_SUBMIT` -> `RECON_SYNC`.
*   **Regla de Oro**: Si una señal desaparece, el TraceBullet debe indicar el último "Borde" alcanzado.

### Reglas de Operación
1.  **Regla de Oro del Silencio**: Si hay 0 trades en Fast-Track, revisar flags y gates antes que el mercado.
2.  **Flytest**: Validación de notional/precisión. BTC siempre falla en Testnet (min $100).
3.  **Agnosticismo**: Prohibido thresholds distintos para SOL vs LTC (Anti-Overfitting).

## ⚠️ Gotchas Críticos
1. **Symbol Normalization**: Usar siempre `normalize_symbol()`.
2. **Historian 0 trades**: Verificar `confirm_close` en PositionTracker.
3. **Stagnation Profit-Aware**: NUNCA cerrar trades ganadores por estancamiento.
4. **Binance -2021**: OCO rechazado si TP/SL ya están en precio.
5. **Fee Accounting**: Total = entry_fee + exit_fee (Calculado en `VirtualExchange`).
6. **No Fast-Track**: El uso de `--fast-track` está deprecado. Usar `TRACE_BULLET_ACTIVE=1` para validación de flujo y detección de "Alpha Starvation".
7. **Micro Absorption Direction**: Absorción vota en dirección OPUESTA al CVD agresivo (buyers absorbed → DOWN, sellers absorbed → UP). Score > 0 para contribuir al régimen.
8. **Footprint Z ≠ VWAP Z**: `reversal_signal["z_score"]` es el FOOTPRINT cross-sectional Z (delta magnitude). El VWAP Z-score viene de `context_registry.get_vwap_zscore()`. NUNCA usar footprint Z para value_position.
9. **IN_VALUE Rotation Targets**: SL y TP deben ser ATR-relativos al ENTRY PRICE, no a VWAP/VAH/VAL. Si LONG a Z=0.5, VAH está solo 0.5σ arriba (TP muy corto) pero VAL está 1.5σ abajo (SL muy lejos).
10. **No Bloquear IN_VALUE**: Bloquear trades destruye señal. Mejor routing correcto: IN_VALUE → rotation (continuación) con targets apropiados.
11. **🔴 L2 Data Required for Absorption Backtest**: Sin order book (L2), el `FootprintRegistry` infiere delta desde trades (L1). La absorción se "adivina" estadísticamente, no se observa directamente. Cualquier backtest de absorción sin L2 es inválido para certificar alpha.
- 2026-05-11T21:40:21.114120 | edge-audit | L2 & price ingest completed, CSVs removed.

## 🎯 Objetivo de la Sesión Actual (CERRADA)
*   **Meta**: Certificar Contabilidad del Slim Exit Engine (V10.2). (LOGRADO ✅)
*   **Resultado**: Se corrigió el bug de timestamps en el Historian/PositionTracker. El Auditor ahora puede separar ejecuciones individuales, permitiendo una auditoría real de los Journeys.
*   **Siguiente paso**:
    1. Iniciar una **nueva ventana de conversación** para limpiar contexto.
    2. Auditar el rendimiento real de la estrategia AMT V10 con la contabilidad corregida.
- 2026-05-13T15:20:00.000000 | session-close | Slim Exit Engine deployed. Codebase purified. Awaiting Stress Test.

132. **Professional Symmetry**: En crypto-scalping de alta frecuencia, la simetría 1:1 es vital para proteger el Win Rate. Nunca usar SL < 0.45% (Noise Floor) en activos como LTC para evitar el ruido estocástico.
133. **Alpha Fusion (Composite Signals)**: La confluencia de escenarios AMT es un evento de baja frecuencia pero alta convicción. Estas señales deben tener prioridad absoluta.
