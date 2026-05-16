# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Dual-Core (Reversión/Continuación) con Inercia de Micro-Flujo.
*   **Current Branch**: `v8.1-unified-decision-dna`
*   **Active Mode**: Multi-Coin Agnostic (LTC, SOL, BTC Certified).
*   **Active Alpha**: **AMT V10 Alpha** (Certified Generalized).

## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

### 1. Capa de Hierro (Infraestructura) — [CERTIFICADA ✅]
*   **UDT Forensics (v8.1)**: **Unified Decision DNA** operacional. Autopsias automáticas en `EXECUTED/ERROR`.
*   **Hito Actual**: **Arquitectura Zero-Necrosis**. Eliminado `fast_track`, `tracker` y `shadow_sl`.
*   **Métrica de Estrés**: Trazabilidad asíncrona validada en ventanas de 500ms (Phase 2).
*   **Latency Guard**: Zero-interference logging via memory-resident DNA traces.

### 2. Capa de Cristal (Estrategia / Alpha) — [WATCH (Alpha Rescue) 🔄]
*   **AMT V10 Alpha**: Certified Generalized (LTC 63.2% WR).
*   **Hito Actual**: **UDT-Guided Alpha Audit**.
*   **Métrica Forense**: Confirmada "Alpha Starvation" (83% Timeout) vía autopsias UDT (630ms capture).
*   **Symmetry**: 1:1 RR con 0.45% Noise Floor obligatorio.

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
5.  **CALIBRACIÓN ALPHA — PRÓXIMO PASO**: Ajuste de Phase 2 basado en datos UDT.

---

## 🎯 Objetivo de la Sesión Actual (SESIÓN 7 - PLANIFICADA)
*   **Meta**: Resolver "Alpha Starvation" (83% Timeouts) mediante calibración UDT.
*   **Hitos**:
    - [x] Implement Fast-Lane routing for Absorption (bypass Guardian).
    - [x] Repurpose Guardian as a Tactical Confirmation Gate (for Swing/Rotation).
    - [x] Certify Fast-Lane performance (77.3% WR / +0.2455% Exp).
    - [ ] Calibrate dynamic targets (0.45% -> Vol-Adjusted).
    - [ ] **Window Optimization**: Evaluar si 500ms es insuficiente para micro-flujo.

---

## ⚠️ Gotchas Críticos
1. **Symbol Normalization**: Usar siempre `normalize_symbol()`.
2. **Historian 0 trades**: Verificar `confirm_close` en PositionTracker.
3. **Stagnation Profit-Aware**: NUNCA cerrar trades ganadores por estancamiento.
4. **Binance -2021**: OCO rechazado si TP/SL ya están en precio.
5. **No Fast-Track**: Deprecado. Usar `TRACE_BULLET_ACTIVE=1` para validación de flujo.
6. **L2 Data Requirement**: Backtests de absorción sin L2 son inválidos.
7. **Micro Absorption Direction**: Vota en dirección OPUESTA al CVD agresivo.
8. **IN_VALUE Rotation**: Targets deben ser ATR-relativos al ENTRY, no a la estructura VA.
9. **Position Limit = 1/symbol**: Bloquea señales concurrentes. Ver `🚫 SIGNAL_REJECTED`.

- 2026-05-15T07:45:00.000000 | session-close | UDT Forensic System certified. Codebase purified. Awaiting Alpha Calibration.
- 2026-05-15T10:00:00.000000 | session-update | Fast-Lane deployed. 77.3% WR confirmed. Guardian repurposed.

### [v8.1-unified-decision-dna] - 2026-05-15
#### Added
- **AMT Fast-Lane Architecture**: Decoupled high-speed signals (Absorption, Failed Breakout) from tactical confirmation delays.
- **Tactical Confirmation Gate**: Repurposed the old Absorption Guardian into a generic, docstring-defined conviction filter for non-scalping (Swing/Rotation) scenarios.
- **UDT Forensic DNA**: Full integration of Unified Decision DNA into `historian.db`.

#### Changed
- **Absorption Routing**: Moved `TacticalAbsorptionV2` to Fast-Lane execution path in `SetupEngine`.
- **Forensic Auditor**: Renumbered sections in `setup_edge_auditor.py` (Section [4] is now Trace Audit).

#### Certified
- **Naked Edge Audit**: Confirmed 77.3% WR and +0.2455% Gross Exp for Absorption signals when bypassing tactical confirmation.
- **Fast-Lane Parity**: Verified production code parity with theoretical naked performance.
- 2026-05-15T18:22:18.750788 | session-close | L2 & price ingest completed, CSVs removed.
