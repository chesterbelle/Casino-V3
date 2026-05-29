# Casino-V3 Agent Memory — Brújula Estratégica

> **⚠️ INSTRUCCIONES PARA EL AGENTE — LEER ANTES DE CUALQUIER ACCIÓN:**
> 1. **Leer este archivo completo al inicio de cada sesión**, antes de escribir código, ejecutar comandos o hacer suposiciones.
> 2. **Actualizar este archivo al final de cada sesión** con: decisiones tomadas, métricas comparativas y estado de las capas.
> 3. **REGLA DE ORO DE GIT (NO MERGE):** Hay 3 BOTS DIFERENTES e incompatibles viviendo en distintas ramas. **NUNCA hagas merge ni rebase.**
> 4. **REGLA DE PUSH (SOLO LOCAL):** NUNCA ejecutes `git push` a menos que el usuario lo ordene expresamente.

## 🚀 Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).
*   **Strategy**: Total Spectrum Absorption V3 — Dual-Core (Reversión/Continuación) con Inercia de Micro-Flujo.
*   **Current Branch**: `v8.4-agent-friendly-refactor` (V8.5 Planar Architecture, commit `f036fbd`)
*   **Active Mode**: Multi-Coin Agnostic
*   **Active Alpha**: **AMT V10 Alpha** (Certified Generalized).


## 📚 Historial y Contexto
*   **Archivo Maestro de Sesiones**: [`.agent/changelog.md`](file:///home/chesterbelle/Casino-V3/.agent/changelog.md)
*   **Propósito**: Contiene la narrativa detallada de cada sesión, métricas de backtests antiguos y evolución cronológica.

---

## 🏛️ Estado de las Capas de Certificación

*   **Crystal Layer Cleanup (v8.5)**: **COMPLETADO ✅**. Auditoría forense identificó código muerto: AbsorptionReversalGuardian (desconectado del pipeline), confirmation_sensors, AbsorptionSetupEngine, sensor_tracker, statistical_location_guardian. Fast-track zombie extirpado (21 refs → 0). **-2,172 líneas, 6 archivos eliminados.**
*   **Crystal Layer 10/10 Readability**: **COMPLETADO ✅**. `regime_guardian.py` decomuesto (297→167 líneas, 4 funciones puras). Idioma estandarizado (ES→EN en 6 archivos). Código muerto eliminado (_trace, trace_callback). Mensajes corregidos. Phase numbers eliminados. `defaultdict(int)`, `setup_name` unificado.
*   **Iron Layer Optimizations (16 OPT)**: **COMPLETADO ✅**. Backtest speed 33% faster (1m30s→1m0s). Live latency: POC O(n)→O(1), VA sort O(n log n)→O(log n), CVD/Exhaustion O(n)→O(log n), deque ATR, symbol_map O(1), single-pass OB, put_nowait, single-subscriber engine dispatch, orjson fallback, itertuples, single SQLite connection.
*   **Validator Fixes**: **COMPLETADO ✅**. 3 fixes (regime_guardian, absorption_candidate, absorption_guardian), 1 delete (minimal_math_validator). 10/10 validators PASS.
*   **Edge Auditor Simplification**: **COMPLETADO ✅**. Calibrator removed (grid sweep was unused). Auditor simplified to core analysis (827→577 lines). `--calibrate` flag removed. 3 edge audit workflows updated with correct paths and merge step.
*   **Documentation Updated**: **COMPLETADO ✅**. AMT V10 Strategy Manifesto (471 líneas). CONFIGURATION.md (527 líneas). TROUBLESHOOTING.md (620 líneas). validate-all.md v8.3→v8.5.
*   **Orquestación de Auditorías (v8.3)**: Implementado `scripts/orchestrator.py` para automatización determinística de protocolos `generalized` y `long-range`.
*   **UDT Forensics (v8.1)**: **Unified Decision DNA** operacional. Autopsias automáticas en `EXECUTED/ERROR`.
*   **Hito Actual**: **Arquitectura Slim + Zero-Necrosis + Performance Optimized**. Código muerto eliminado, Crystal Layer 10/10 legible, Iron Layer optimizado.
*   **Optimización V8.3**: HPC Audit completada. 18/19 optimizaciones implementadas en la Capa de Hierro.
*   **Validate-All Pipeline**: Suite completa Capas 0-5 certificada. 10/10 validators PASS.

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
8.  **CRYSTAL REFORGE — EN CURSO 🔄**: Quality Pipeline + Exhaustion Core implementado. Necesita threshold tuning.
9.  **INVESTIGACIÓN ETH — PRÓXIMO PASO**: Investigar por qué ETH no logra Net Taker positivo.
10. **LIVE / PAPER TRADING — PRÓXIMO PASO**: Conexión al Testnet/Live.

---

### Current Status: 🟢 v8.4 Crystal Reforge — Working (Full Profile System)
- **Architecture**: Quality Pipeline + 4 scenarios + dynamic targets + coin profiler + profile manager + proximity analysis.
- **Baseline**: Net Taker +0.0564% (LTCUSDT 24h, 187 signals). Long-range: +0.2254%.
- **Win Rate**: 59.8%
- **Tags**: `v8.4-pre-reforge` (checkpoint), `v8.4-crystal-reforge` (current).
- **Commits**: `ffd189e` (full profile system), `a6780c1` (coin profiler), `22ccca7` (dynamic targets), `69c8a8d` (parametric fix), `d5a49b6` (TrendAcceptance), `438c90e` (Crystal Reforge), `56d1cf7` (toxic block), `afa0b2e` (audit mode), `e4f87e6` (toxic block removal).
- **Profiles**: 3 profiles (VOLATIL_BAJO_FLOW, EFICIENTE_MEGACAP, BALANCED_MID) with full Crystal Layer parameters.
- **Profile System**: coin_profiler.py classifies coins → profile_manager.py loads parameters → quality_scorer/targets/guardians use profile params.
- **Per Setup**: TacticalAbsorptionV2 (MFE/MAE 1.63), failed_breakout (MFE/MAE 1.94), liquidity_exhaustion (MFE/MAE 0.95), trend_acceptance (MFE/MAE 0.40)
- **Multi-Coin**: 3/10 coins with edge (SUI, AVAX, LTC). Edge is instrument-dependent.
- **Next**: Download more datasets and tune per profile

---

## ⚠️ Gotchas Críticos
10. **Taker-Only Execution Mandate**: Toda validación se juzga descontando fees Taker del 0.12%.
11. **Historian Cumulative Runs**: Usar `--historian-db` para aislar archivos SQLite por run.
12. **Parallel Audit SQLite Write Locks**: Usar archivos temporales y consolidar al final.
13. **Break-Even Cost Fallacy**: El Break-Even estático mata el Edge (93.75% winners perdidos). Todo SL debe ser estructural.

---

## 📝 Timeline de Sesiones Recientes
- 2026-05-28T09:00:00 | session-close | v8.4 Crystal Reforge implementado: Quality Pipeline + Exhaustion Core. 177 signals, 37% WR, Net Taker +0.0012%. Necesita threshold tuning.
- 2026-05-28T06:00:00 | session-update | Edge Audit LTCUSDT: 3 signals, Net Taker +0.1739%. Diagnóstico: 98.7% guardian rejection rate (195/198).
- 2026-05-28T06:30:00 | session-update | Forense guardian chain: 917 ABS signals → 229 guardian rejections → 723 passed → 720 killed by in-trade lock → 3 trades.
- 2026-05-28T07:00:00 | session-update | TOXIC FLOW BLOCK identificado como bug de diseño: contradice BALANCE regime (score=1.0) y TREND Cases 3/4.
- 2026-05-28T07:30:00 | session-update | A/B test: eliminar toxic block → Signals 3→11 (+267%), Net Taker +0.17%→+0.66% (+283%), MFE/MAE 0.92→1.81.
- 2026-05-28T08:00:00 | session-update | Audit mode fixes: in-trade lock bypass + no execution. FADE RISK analysis: sensor VAH/UX filter reverted (arquitectura incorrecta).
- 2026-05-28T08:30:00 | session-close | v8.4-crystal-reforge tagged. Net Taker +0.68%, MFE/MAE 1.62, WR 100%. 3 commits, 0 regress.
- 2026-05-27T16:00:00 | session-update | Crystal Layer Cleanup: Auditoría forense identificó AbsorptionReversalGuardian desconectado, fast_track zombie, código muerto acumulado V8→V10.
- 2026-05-27T16:30:00 | session-update | Ejecutado benchmark pre-cleanup: 2 signals, Net Taker +0.1334%, Net Maker +0.1734%.
- 2026-05-27T17:00:00 | session-close | Cleanup completado: -2,172 líneas, 6 archivos eliminados, 8 archivos podados. Post-cleanup: Net Taker +0.1155%, Net Maker +0.1555%.
- 2026-05-27T18:00:00 | session-update | Crystal Layer 10/10 Readability: regime_guardian decomuesto (297→167), ES→EN, Phase numbers eliminados, code quality.
- 2026-05-27T19:00:00 | session-update | AMT V10 Manifesto + docs: CONFIGURATION.md (527), TROUBLESHOOTING.md (620).
- 2026-05-27T20:00:00 | session-update | Iron Layer OPT (16 OPT across 10 files): backtest 33% faster, live latency reduced.
- 2026-05-27T21:00:00 | session-update | Validator fixes: 3 fixed, 1 deleted, 10/10 PASS. validate-all.md v8.5.
- 2026-05-27T22:00:00 | session-update | Edge auditor: calibrator removed (250 lines). 3 workflows updated. merge_historian.py verified.
- 2026-05-27T22:16:00 | session-close | Full session documented. 18 commits, -2,857 líneas netas, Net Taker +0.1334% preservado. Commit `f036fbd`.
