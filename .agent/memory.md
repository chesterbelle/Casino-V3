# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Dual-Core (Reversión/Continuación) con Inercia de Micro-Flujo.
*   **Current Branch**: `v7.3.0-certified-v3.2-inertia`
*   **Active Mode**: Multi-Coin Agnostic (LTC, SOL, BTC Certified).


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

### 2. Capa de Cristal (Estrategia / Alpha) — [RE-CALIBRACIÓN BEAR 📉]
*   **Propósito**: Validación de Edge (Expectancia Bruta > 0.12%), Win Rate, MAE/MFE.
*   **Hito Actual (v7.3.0c)**: **Certificación de Integridad Estructural para BEAR Re-calibration**.
*   **Tabla Comparativa de Estrategias (Baselines)**:

| Estrategia | Estado | Gross Expectancy | Net (Maker) | WR% | Razón de Cambio |
|------------|--------|------------------|-------------|-----|-----------------|
| **V3.4-Crystal**| Obsoleta | +0.1548%| +0.0748%| 56.2%| VWAP Z correcto + Rotation (ATR Targets). |
| **V3.4c-Integrity**| **BASELINE** | **TBD** | **TBD** | **TBD** | 🚀 **Layer 0-3 CERTIFIED**. Pipeline estructuralmente estable para re-calibración BEAR. |

*   **Lecciones Estratégicas**:
    *   **Metadatos Estructurales**: `SetupEngineV4` ahora inyecta niveles POC/VAH/VAL correctamente desde el `ContextRegistry`.
    *   **Paralelismo Real**: Validada la ejecución concurrente de múltiples posiciones sin colisiones de estado en el reactor event-driven.
    *   **Auto-Healing Proactivo**: `DriftAuditor` sincroniza balance y posiciones via REST fallback si el WebSocket falla (Cooldown=0 para validación).

### 3. Capa de Acero (Resiliencia / Ejecución) — [CERTIFICADA ✅]
*   **Propósito**: PortfolioGuard, Limit Sniper, ExitEngine stacks.
*   **Resiliencia Validada**:
    *   **Chaos Matching**: 100% de integridad en eventos WebSocket bajo carga masiva.
    *   **Auto-Healing**: Recuperación automática de drifts de balance y "Adoptión" de posiciones huérfanas.
    *   **Connectivity Integrity**: Reconexión automática de shards sin pérdida de flujo de órdenes.

---

## 📉 Roadmap: BEAR Strategy Re-calibration
1.  **Analisis de MAE en Downtrend**: Identificar si el SL de 1.0*ATR es suficiente para absorber volatilidad en impulsos bajistas.
2.  **Ajuste de MFE/MAE Ratio**: Calibrar targets de continuación para capturar rotaciones completas al VAL opuesto.
3.  **Filtrado de False Positives**: Evaluar impacto de `Inertia Guard` en señales de absorción durante "Dumping" agresivo.

---

## 🏛️ Estado de las Capas de Certificación (v7.3.0c)
1. **Capa 0 (Data/Math)**: **CERTIFICADA ✅** (Flytest + Guardian Math + Exit Math).
2. **Capa 1 (Decision)**: **CERTIFICADA ✅** (Setup Metadata Enrichment + Registry Parity).
3. **Capa 2 (Execution)**: **CERTIFICADA ✅** (Concurrent OCO + Reactor Reactor).
4. **Capa 3 (Resilience)**: **CERTIFICADA ✅** (Drift Auditor + Connectivity Stress).
5. **Capa 4 (Strategy)**: **EN CURSO 📉** (BEAR Re-calibration).
6. **Capa 5 (Risk)**: **PENDIENTE 🛡️**.

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
*   **Descarga de Datos**: `parity_data_fetcher.py` (Única herramienta autorizada).
*   **L2 Harvester**: `utils/l2_harvester.py` (Recolecta Order Book real cada 100ms para datasets de alta fidelidad).
*   **Data Reset**: `utils/reset_data.py` (Limpieza total de DB y estados JSON para entornos deterministas).
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
*   *Bordes Críticos*: `SENSOR_INGEST` -> `GUARDIAN_CHECK` -> `SETUP_GEN` -> `EXEC_SUBMIT` -> `RECON_SYNC`.
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
