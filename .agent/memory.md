# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Dual-Core (Reversión/Continuación) con Inercia de Micro-Flujo.
*   **Current Branch**: `v8.3-optimized`
*   **Active Mode**: Multi-Coin Agnostic
*   **Active Alpha**: **AMT V10 Alpha** (Certified Generalized).


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

*   **Orquestación de Auditorías (v8.3)**: Implementado `scripts/orchestrator.py` para automatización determinística de protocolos `generalized` y `long-range`. Eliminación de ejecución manual concurrente.
*   **Repo Sanitization (In Progress)**: Iniciada fase de limpieza y purificación de archivos huérfanos/legacy para mejorar mantenibilidad.
*   **UDT Forensics (v8.1)**: **Unified Decision DNA** operacional. Autopsias automáticas en `EXECUTED/ERROR`.
*   **Hito Actual**: **Arquitectura Zero-Necrosis**. Eliminado `fast_track`, `tracker` y `shadow_sl`.
*   **Métrica de Estrés**: Trazabilidad asíncrona validada en ventanas de 500ms (Phase 2).
*   **Latency Guard**: Zero-interference logging via memory-resident DNA traces.
*   **Optimización V8.3**: HPC Audit completada. 18/19 optimizaciones implementadas en la Capa de Hierro. Running sums O(1), VWAP residuals O(1), semáforo de concurrencia, task tracking, event-based parking, template dict, sync hot paths, peak incremental, QueueHandler logging, aiosqlite, __slots__ OpenPosition.
*   **Validate-All Pipeline (Mayo 26)**: Suite completa Capas 0-5 certificada. 3 bugs corregidos durante validación (self.clock, orchestrator truncado, aiosqlite faltante). Bot operacionalmente seguro.

### 2. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA 🟢 (4-Coin Net Taker Positive)]
*   **AMT V10 Alpha**: Audited across 10 crypto assets. 4 certified Net Taker positive (BNB, SOL, SUI, AVAX).
*   **Hito Actual**: **Multi-Window Grid Discovery** — Ventana de 4h elimina Timeouts y desbloquea Net Taker positivo.
*   **Métrica Forense (4h Window)**: BNB +0.107% (1.2% target), SOL +0.28% (1.2%), SUI +0.08% (1.2%), AVAX +0.12% (1.2%).
*   **Sweet Spot**: Target 1.0%-1.2% TP/SL simétrico con ventana de 4h. Ventanas < 2h generan Timeouts que destruyen expectancia.
*   **ETH PROBLEM**: Único activo que no logra Net Taker positivo en ninguna combinación window/target debmos investigar porque.

### 3. Capa de Acero (Resiliencia / Ejecución) — [CERTIFICADA ✅]
*   **Slim Exit Engine (v10.2)**: Salidas tácticas vía Maker (Limit Orders) certificadas.
*   **Concurrency Guard**: Lock de símbolos (`_inflight_symbols`) activo.
*   **Auto-Healing**: Recuperación de drifts y adopción de posiciones huérfanas funcional.

---

## 📉 Roadmap: CAPA 0 → Absorption Alpha Validation
1.  **DATA/MATH — COMPLETADO ✅**: Pipeline L2 SQLite operativo.
2.  **AMT V10 ARCH — COMPLETADO ✅**: Escenarios AMT integrados.
3.  **EXECUTION STABILITY — COMPLETADO ✅**: Slim Exit Engine sincronizado.
4.  **UDT FORENSICS — COMPLETADO ✅**: Sistema de autopsias unificado (Rama 8.1).
5.  **CALIBRACIÓN ALPHA — COMPLETADO ✅**: Edge certificado universalmente en 10 criptomonedas.
6.  **LIVE / PAPER TRADING — PRÓXIMO PASO**: Conexión al Testnet/Live para validar slippage real y ejecución WebSocket.

---

### Current Status: 🟢 Slim & Certified (Phase 900+ Optimized)
- **Architecture**: `v8.2-slim` deployed. 4 pillars reduced to 2 (Scale Out + Micro-Z Reversal).
- **Baseline**: Alpha "Naked" (Sin BE ni Trailing).
- **Persistence**: 100% Signal Persistence verified.
- **Exit Strategy**: Removed noise (BE, Trailing). Focused on structural exit.

---

### 🏛️ Auditoría Forense: Transición a Arquitectura Slim
*   **Decisión Estratégica**: Tras auditar `historian_final_merged.db`, descubrimos que el pilar `Break-Even` eliminaba al **93.75% de nuestros trades ganadores**. Se decidió eliminar por completo el `Break-Even` y `Trailing Stop`.
*   **Cambio de Paradigma**: Pasamos de una gestión "Geométrica" (ATR-basada, reactiva al precio) a una gestión "Estructural" (Micro-Z Reversal, reactiva al flujo).
*   **Justificación**: Si un setup de entrada tiene Alpha real, no necesita "ayudas artificiales" que solo aumentan la varianza y recortan la cola derecha de la distribución de beneficios.

---

## 📉 Roadmap: CAPA 0 → Absorption Alpha Validation
1.  **DATA/MATH — COMPLETADO ✅**: Pipeline L2 SQLite operativo.
2.  **AMT V10 ARCH — COMPLETADO ✅**: Escenarios AMT integrados.
3.  **EXECUTION STABILITY — COMPLETADO ✅**: Slim Exit Engine sincronizado.
4.  **UDT FORENSICS — COMPLETADO ✅**: Sistema de autopsias unificado (Rama 8.1).
5.  **CALIBRACIÓN ALPHA —  CASICOMPLETADO ✅**: Edge certificado universalmente en 10 criptomonedas. con execpcion de ETH
6.  **EXIT ENGINE SLIM — COMPLETADO ✅**: Purga de pilares ruidosos.
7.  **INVESTIGACION— PRÓXIMO PASO**: investigar porque sirve en todos menos ETH.

---

## ⚠️ Gotchas Críticos
...
10. **Taker-Only Execution Mandate**: ...
11. **Historian Cumulative Runs**: ...
12. **Parallel Audit SQLite Write Locks**: ...
13. **Break-Even Cost Fallacy**: El Break-Even estático mata el Edge de absorción (93.75% de winners perdidos en backtest). Todo SL debe ser estructural o basado en cambio de régimen (Micro-Z).

- 2026-05-24T09:30:00.000000 | session-update | Auditoría forense del Break-Even (93.75% de winners perdidos).
- 2026-05-24T10:00:00.000000 | session-close | Purga de pilares: Eliminados Break-Even y Trailing Stop. SlimExitEngine operando solo con Scale Out y Micro-Z Reversal. Arquitectura Slim certificada.
- 2026-05-25T15:00:00.000000 | session-update | Repo Sanitization: Eliminados archivos .bak y exit_edge_auditor.py. Workflows actualizados para apuntar solo al setup_edge_auditor.
- 2026-05-25T15:20:00.000000 | session-update | CLI Refactor: Reemplazado flag implícito y --audit por argumento obligatorio --run-type (audit|trade) en main.py y backtest.py para mitigar riesgos de ejecución accidental.
- 2026-05-25T16:10:00.000000 | session-update | Smart Orchestrator: Refactorizado scripts/orchestrator.py para implementar búsqueda estricta de datasets (evitando fallos silenciosos), aislamiento de logs y un monitor de progreso I/O (Heartbeat) que previene la ceguera durante ejecuciones largas.
- 2026-05-25T16:15:00.000000 | session-close | Preparación completada. CLI segura y Orquestador inteligente implementados. Siguiente paso: Sesión de análisis de mercado/borde.
