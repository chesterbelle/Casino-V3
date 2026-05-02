# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: LTA V7 (Structural Absorption) — Unificación de Contexto LTA + Motor Abs. V2.1.
*   **Current Branch**: `v7.1.0-lta-v7-structural-absorption`
*   **Active Mode**: Multi-Coin Agnostic (Evolución de SOL, LTC, ADA).


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos, análisis de fallos (root cause) y la evolución cronológica de las fases (Phase 1200, 2300, etc.).
*   **Uso**: Consultar cuando se necesite profundizar en el "por qué" de una decisión arquitectónica o recuperar datos comparativos que no estén en la Brújula.


---

## 🏛️ Estado de las Capas de Certificación

### 1. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **Propósito**: Paridad 1:1, Resiliencia del Historian, Latencia < 50ms, Integridad Contable.
*   **Hito Actual (v7.1.0)**: Certificada con Estabilidad Reactiva y Cierre de Posiciones Fantasma.
*   **Tag de Restauración**: `v7.1.0-reactive-stability-pass`
*   **Métrica de Estrés**: Loop Lag: **1.01ms** bajo carga de 2,000 eventos/seg.
*   **HFT Latency Telemetry (T0-T4)**:
    *   `t0`: Tick exchange | `t1`: Decision | `t2`: Submit | `t3`: Fill confirm | `t4`: PositionTracker.
    *   *Resilient Logic*: Fallbacks en `historian.py` y `position_tracker.py` para evitar NULLs y Silent Skips.

### 2. Capa de Cristal (Estrategia / Alpha) — [EN EVOLUCIÓN 💎]
*   **Propósito**: Validación de Edge (Expectancia Bruta > 0.12%), Win Rate, MAE/MFE.
*   **Tabla Comparativa de Estrategias (Baselines)**:

| Estrategia | Estado | Gross Expectancy | Net (Maker) | WR% | Razón de Cambio |
|------------|--------|------------------|-------------|-----|-----------------|
| **LTA V6** | Obsoleta | -0.0176% | -0.0976% | 49.5% | No viable en 2024. |
| **Abs. V2.1**| **ACTUAL** | **+0.1230%** | **+0.0430%** | 57.1% | ✅ CERTIFICADA. |

*   **Lecciones Estratégicas**:
    *   **Root Cause de Erosión**: Fees consumen 130% del PnL bruto en Market (0.066%/RT vs 0.24% MFE).
    *   **Agnosticismo**: Prohibido ajuste de parámetros por moneda. La lógica debe ser global.

### 3. Capa de Acero (Resiliencia / Ejecución) — [EN DESARROLLO ⚔️]
*   **Propósito**: PortfolioGuard, Limit Sniper, ExitEngine stacks.
*   **Exit Engine (5-Layer Stack)**:
    *   Layer 5: **Catastrophic Stop** | Layer 4: **Thesis Invalidation** | Layer 3: **Valentino (SCE)** | Layer 2: **Shadow Protection** | Layer 1: **Drain**.
    *   *Regla de Hierro (Anti-Esquizofrenia)*: Nunca habilitar capas que compitan entre sí. Usar siempre un `ACTIVE_EXIT_PROFILE` único:
        *   **EXPRIMIDOR**: L2 (Trailing/Winner Catcher) activo. L4 y L3 apagados. Ideal para Micro-Scalping.
        *   **FRANCOTIRADOR**: L4 (Invalidación por Flujo) activo. L2 apagado. Ideal para Reversiones Puras.
        *   **ESCALADOR**: L3 (Scale-out) activo. L2 apagado. Ideal para asegurar 50% de ganancia temprana.
*   **Drain Phase**: Solo con `--close-on-exit`. Bloquea entradas cuando `elapsed >= timeout - drain_duration`.

---

## 🗺️ Mapa de Arquitectura

### Componentes Core
*   `SetupEngine`: Detección táctica (Trapped Traders, Divergence).
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
*   **`--fast-track`**: Bypasea gates estructurales para testeo. **NUNCA en producción**.
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

## 🗺️ Roadmap Capa de Cristal (Alpha Optimization)
- [x] **Fase 1: Dynamic Limit Sniper**: Maker-fee optimization con lógica de chase y telemetría TraceBullet completa.
- [ ] **Fase 2: Guardian Scoring**: Transición de veto binario a scoring de confianza fuzzy (En discusión).
- [ ] **Fase 3: Location Heatmap**: Refinamiento alpha contextual basado en zonas de liquidez (En discusión).

## ⚠️ Gotchas Críticos
1. **Symbol Normalization**: Usar siempre `normalize_symbol()`.
2. **Historian 0 trades**: Verificar `confirm_close` en PositionTracker.
3. **Stagnation Profit-Aware**: NUNCA cerrar trades ganadores por estancamiento.
4. **Binance -2021**: OCO rechazado si TP/SL ya están en precio.
5. **Fee Accounting**: Total = entry_fee + exit_fee (Calculado en `VirtualExchange`).

---

## 🎯 Objetivo de la Siguiente Sesión
*   **Principal (Macro)**: Validar el ciclo completo (End-to-End) desde la detección de absorción en los workers hasta la ejecución del `Croupier` en modo "Exprimidor".
*   **Secundario (Micro)**: Ejecutar un Live-Simulation (demo) para observar cómo el "Winner Catcher" expande el TP y ajusta el Trailing Stop en tiempo real.
