# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Dual-Core (Reversión/Continuación) con Inercia de Micro-Flujo.
*   **Current Branch**: `v8.4-agent-friendly-refactor` (V8.5 Planar Architecture, commit `79d4875`)
*   **Active Mode**: Multi-Coin Agnostic
*   **Active Alpha**: **AMT V10 Alpha** (Certified Generalized).


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

*   **Crystal Layer Cleanup (v8.5)**: **COMPLETADO ✅**. Auditoría forense identificó código muerto: AbsorptionReversalGuardian (desconectado del pipeline), confirmation_sensors, AbsorptionSetupEngine, sensor_tracker, statistical_location_guardian. Fast-track zombie extirpado (21 refs → 0). **-2,172 líneas, 6 archivos eliminados.** Commit `79d4875`.
*   **Orquestación de Auditorías (v8.3)**: Implementado `scripts/orchestrator.py` para automatización determinística de protocolos `generalized` y `long-range`.
*   **UDT Forensics (v8.1)**: **Unified Decision DNA** operacional. Autopsias automáticas en `EXECUTED/ERROR`.
*   **Hito Actual**: **Arquitectura Slim + Zero-Necrosis**. Código muerto eliminado. Solo queda código activo y funcional.
*   **Optimización V8.3**: HPC Audit completada. 18/19 optimizaciones implementadas en la Capa de Hierro.
*   **Validate-All Pipeline (Mayo 26)**: Suite completa Capas 0-5 certificada.

### 2. Capa de Cristal (Estrategia / Alpha) — [CERTIFICADA 🟢 (4-Coin Net Taker Positive)]
*   **AMT V10 Alpha**: Audited across 10 crypto assets. 4 certified Net Taker positive (BNB, SOL, SUI, AVAX).
*   **Hito Actual**: **Multi-Window Grid Discovery** — Ventana de 4h elimina Timeouts y desbloquea Net Taker positivo.
*   **Métrica Forense (4h Window)**: BNB +0.107% (1.2% target), SOL +0.28% (1.2%), SUI +0.08% (1.2%), AVAX +0.12% (1.2%).
*   **Sweet Spot**: Target 1.0%-1.2% TP/SL simétrico con ventana de 4h.
*   **ETH PROBLEM**: Único activo que no logra Net Taker positivo en ninguna combinación window/target.

### 3. Capa de Acero (Resiliencia / Ejecución) — [CERTIFICADA ✅]
*   **Slim Exit Engine (v10.2)**: Salidas tácticas vía Maker (Limit Orders) certificadas.
*   **Concurrency Guard**: Lock de símbolos (`_inflight_symbols`) activo.
*   **Auto-Healing**: Recuperación de drifts y adopción de posiciones huérfanas funcional.

---

## 📉 Roadmap: CAPA 0 → Absorption Alpha Validation
1.  **DATA/MATH — COMPLETADO ✅**: Pipeline L2 SQLite operativo.
2.  **AMT V10 ARCH — COMPLETADO ✅**: Escenarios AMT integrados.
3.  **EXECUTION STABILITY — COMPLETADO ✅**: Slim Exit Engine sincronizado.
4.  **UDT FORENSICS — COMPLETADO ✅**: Sistema de autopsias unificado.
5.  **CALIBRACIÓN ALPHA — COMPLETADO ✅**: Edge certificado universalmente en 10 criptomonedas (excepto ETH).
6.  **EXIT ENGINE SLIM — COMPLETADO ✅**: Purga de pilares ruidosos.
7.  **CRYSTAL CLEANUP — COMPLETADO ✅**: Código muerto eliminado (-2,172 líneas).
8.  **INVESTIGACIÓN ETH — PRÓXIMO PASO**: Investigar por qué ETH no logra Net Taker positivo.
9.  **LIVE / PAPER TRADING — PRÓXIMO PASO**: Conexión al Testnet/Live.

---

### Current Status: 🟢 Slim, Certified & Clean (Zero-Necrosis)
- **Architecture**: V8.5 Planar. Crystal Layer purged of dead code.
- **Baseline**: Net Taker +0.1155%, Net Maker +0.1555% (LTCUSDT single-coin).
- **Commit**: `79d4875` on `v8.4-agent-friendly-refactor`.
- **Exit Strategy**: Scale Out + Micro-Z Reversal only.

---

## ⚠️ Gotchas Críticos
10. **Taker-Only Execution Mandate**: Toda validación se juzga descontando fees Taker del 0.12%.
11. **Historian Cumulative Runs**: Usar `--historian-db` para aislar archivos SQLite por run.
12. **Parallel Audit SQLite Write Locks**: Usar archivos temporales y consolidar al final.
13. **Break-Even Cost Fallacy**: El Break-Even estático mata el Edge (93.75% winners perdidos). Todo SL debe ser estructural.

---

## 📝 Timeline de Sesiones Recientes
- 2026-05-27T16:00:00 | session-update | Crystal Layer Cleanup: Auditoría forense identificó AbsorptionReversalGuardian desconectado, fast_track zombie, código muerto acumulado V8→V10.
- 2026-05-27T16:30:00 | session-update | Ejecutado benchmark pre-cleanup: 2 signals, Net Taker +0.1334%, Net Maker +0.1734%.
- 2026-05-27T17:00:00 | session-close | Cleanup completado: -2,172 líneas, 6 archivos eliminados, 8 archivos podados. Post-cleanup: Net Taker +0.1155%, Net Maker +0.1555% (positivo preservado). Commit `79d4875`.
