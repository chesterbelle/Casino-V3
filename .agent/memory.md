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

### 2. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA 🟢 (LTC Taker-Only)]
*   **AMT V10 Alpha**: Certified in LTC (Taker-Only edge verified at 0.9%/1.0% under a 1h holding period).
*   **Hito Actual**: **Mapeo de Constantes Microestructurales (Long-Range Audit)**.
*   **Métrica Forense**: Win Rate de 58.2% y Net Taker-Only de +0.0442% bajo targets uniformes de 1.0%/1.0% (1h window).
*   **Symmetry**: Calibración fija de 0.9% TP / 0.6% SL (1.5:1 RR) con clamping temporal de 1 hora.

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

### Current Status: 🟢 Certified (Fast-Lane Active)
- **Architecture**: `v8.1.0` deployed. `TacticalAbsorptionV2` now operates on a **Fast-Lane** (0ms latency).
- **Baseline**: +0.1642% Gross Expectancy / +0.0442% Net Taker-Only (LTC 9-Day Dataset at 1.0% TP/SL).
- **Persistence**: 100% Signal Persistence verified.
- **Guardian Layer**: Repurposed as a **Tactical Confirmation Gate** for Swing/Rotation setups.

### Performance Baseline (Last Audit)
| Symbol | Strategy | WR% | Net Taker-Only Exp | Verdict |
|--------|----------|-----|-------------------|---------|
| LTCUSDT| Absorption (0.9%/1h)| 58.7%| +0.0360% | **CERTIFIED** |
| LTCUSDT| Absorption (1.0%/1h)| 58.2%| +0.0442% | **CERTIFIED** |
| Global | AMT Scenarios| 42.9%| -0.1302% | **FAILED** (Needs Calibration) |

### Next Session Objectives
1.  **Harden Setup Engine**: Modify `decision/setup_engine.py` to enforce static 0.9% TP and 0.6% SL targets for TacticalAbsorptionV2.
2.  **Implement Time-Exit**: Code a síncrono 1h (3600s) atomic time-exit in `PositionTracker`/`AdaptivePlayer` or `SlimExitEngine` to prevent decay.
3.  **Mandatory L2 Filter**: Integrate the `L2 Depth Wall (>2.0 Ratio)` confirmation gate on the TacticalAbsorptionV2 entry path to slash MAE to 0.358%.
4.  **Cross-Instrument Certification**: Execute the 10-coin battery (`@/generalized-edge-audit`) to prove that the armored bot is globally net-taker profitable!

---

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
10. **Taker-Only Execution Mandate**: Toda rentabilidad y viabilidad del Alpha se establece estrictamente bajo ejecución **Taker Only** (roundtrip fees de 0.12% total). NUNCA basar viabilidad comercial en Limit Sniper u órdenes Maker pasivas. La expectancia neta Taker debe ser positiva para certificar un setup.

- 2026-05-15T07:45:00.000000 | session-close | UDT Forensic System certified. Codebase purified. Awaiting Alpha Calibration.
- 2026-05-15T10:00:00.000000 | session-update | Fast-Lane deployed. 77.3% WR confirmed. Guardian repurposed.
- 2026-05-17T21:11:00.000000 | session-close | Ran LTC long-range audits and DOGE pilot backtests. Recorded signals and prices to database.

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
- 2026-05-16T00:22:00.000000 | session-close | Fast-Lane bug fixed (Persistence restored). v8.1.0-fast-lane-certified tagged.
- 2026-05-18T02:32:51.321874 | edge-audit | L2 & price ingest completed, CSVs removed.
