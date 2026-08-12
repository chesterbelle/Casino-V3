# Task: Full Endurance 24h (1.4B.5) — Certificación Formal

> **Protocolo**: `.agent/workflows/stress-test.md` Fase B.4 + memory.md Reglas 17/21
> **Fecha**: 2026-08-11 00:44 (hora de lanzamiento)
> **PID**: 71857 | **Log**: `/tmp/endurance_24h.log`

## Configuración del run
- [x] Pre-Flight B.0: emergency_cleanup → 0 posiciones / 0 órdenes (verificado) → reset_data
- [x] Lanzado: `main.py --run-type trade --mode demo --exchange binance --symbol LTCUSDT,SOLUSDT,AVAXUSDT --close-on-exit --timeout 1440`
- [x] Timer graceful: "Stopping in 1440 minutes" (00:44:24)
- [x] Arranque limpio: 0 errores iniciales, 3 símbolos suscritos, candelas fluyendo

## Criterios de éxito (24h)
- [ ] Error Recovery = $0.00 (0 error trades) ← CRÍTICO
- [ ] 0 crashes
- [ ] RAM estable (crecimiento < 50%)
- [ ] Event Integrity = 100% (0 `WS Event UNMATCHED`)
- [ ] Airlock Latency = 100% (0 warnings High Airlock Latency)
- [ ] API Stability = 100% (0 errores `-4120`)
- [ ] Trade Flow Observability = 100% (trazabilidad CREATED→FILLED→RECON_*→CLOSED)
- [ ] Full Exit: tracker vacío tras `--close-on-exit`

## Monitoreo
| Timestamp | Evento | Hallazgo |
|-----------|--------|----------|
| 00:44 | Arranque | OK — 0 errores, 3 símbolos activos |
| 00:49 | Entry AVAX SHORT | OCO TP 6.354 / SL 6.68 — abierto |
| 01:20 | Entry SOL SHORT | OCO TP 75.28 / SL 76.80 — abierto |
| 04:52 | Entry LTC SHORT | OCO TP 44.67 / SL 45.35 |
| 05:18 | Close LTC | SL (ACCOUNT_UPDATE) PnL -0.09 — cierre legítimo. 12 ERROR (-2011) = bracket cleanup tras fill SL (órdenes ya canceladas por Binance) — benigno |
| 05:24 | Check | 0 UNMATCHED, 0 STALL, 0 OCO_ABORT, 0 -4120. Drift $0.00. RSS 208MB estable |
| ~cada 55min | User Stream Rotation | Reciclado proactivo del listen key (rotación intencional) — comportamiento diseñado, sin pérdida de eventos |
| 06:49 | SlimExit AVAX | max_hold 21600s → bracket TP/SL re-colocado (nuevos IDs). -2011 transitorio al cancelar (airlock→local, retry OK). Drift $0.00, 2 pos/2 local |
| 07:20 | SlimExit SOL | Misma compresión, completada OK. Pos Check Exchange=2/Local=2, 2 pos/4 órdenes sin duplicados |
| 08:02 | Close AVAX | **TP (ACCOUNT_UPDATE) PnL +1.08 (Won: True)** — trade 513658723 |
| 09:55 | Entry LTC #2 SHORT | OCO TP 44.67 / SL 45.35 → entry @45.37 |
| 10:03 | Check | 9h17m. RSS 208MB estable. 24 ERROR = solo -2011 transitorios de compresiones SlimExit (benignos) |
| 10:34 | Close LTC #2 | **SL PnL -0.23** — mismo patrón benigno -2011 en cleanup |
| 10:50 | Close SOL | **TP PnL +0.24 (Won: True)** — trade 4180719577 (bracket comprimido 07:20 funcionó) |
| 13:06 | Entry LTC #3 SHORT | OCO TP 44.64 / SL 45.46 → entry @45.00 (trade 1568670303) |
| 14:42 | Check | 13h58m. **4 cerrados: net +1.00 USDT (2W/2L)**. 1 abierto (LTC#3). RSS 201MB. 30 ERROR = todos -2011 benignos. 0 críticos |
| 15:48 | Close LTC #3 | **SL PnL -0.29** — mismo patrón benigno -2011 en cleanup |
| 17:11 | Check | 16h27m. **5 cerrados: net +0.71 USDT (2W/3L)**. Bot FLAT (0 pos/0 órdenes). RSS 217MB. 36 ERROR = todos -2011 benignos. 0 críticos |
| 19:09 | Check | 18h25m. Sin trades nuevos, FLAT. RSS 194MB. Estrategia viva (fires/rechazos POSITION_LIMIT OK) |
| 20:00 | Entry LTC #4 LONG | OCO TP 46.02 / SL 45.33 → entry @45.47 (trade 1568767199) |
| 20:01 | Entry SOL #2 LONG | OCO TP 76.98 / SL 75.60 → entry @76.29 (trade 4181149964) |
| 22:34 | Check | 21h50m. **2 abiertas (LTC#4 LONG, SOL#2 LONG)** con brackets. 5 cerrados net +0.71. RSS 203MB. 36 ERROR benignos. 0 críticos |

## Auditoría post-run
- [x] `utils/audit_logs.py /tmp/endurance_24h.log` → ✅ VERDICT PASS (Stable & Efficient)
- [x] `utils/audit_trade_flow.py --db data/historian.db` → ✅ PASS (7/7 clean, 0 force-closed)
- [x] SESSION SUMMARY: Error Leakage +0.0000 USDT (0 error trades) — CRÍTICO PASS
- [x] 24h completas: 1440.6m (Active 1395m + Draining 45.5m), shutdown graceful
- [x] 0 crashes, RSS 194-217MB estable, 0 UNMATCHED, 0 Airlock Latency, 0 -4120
- [x] Full Exit: 0 pos / 0 órdenes + ledger reconciliation complete
- [x] 7 trades: +0.5287 USDT neto (2W/5L)

## Hallazgos post-run (para decisión de certificación)
1. -2011 ×355: benigno — OCO leg ya cancelado por Binance tras fill SL/TP (cleanup esperado)
2. -2022 ×24: benigno — reduceOnly rechazado, posición ya cerrada (race drain vs TP SOL#2)
3. -4024 ×72: Tier 1 aggressive-limit del SmartClose violó price protection (5% bajo mark) en posición ya cerrada — manejado, 1er caso real
4. -1121 ×4: GOTCHA #20 persistente en ledger reconciliation del shutdown (fetch_open_orders comma-joined)
5. Orphan Hygiene 85.71% (6 "true orphans"): falsos positivos por lag de la vista cacheada del reconciler (los 6 = OCO-leg cancels post-fill, -2011). Criterio workflow <2% NO cumple literalmente pero es artefacto de clasificación
6. Unexplained Variance -1.1633: artefacto — ledger importó 658 COMMISSION históricos del testnet (BTC/ETH/XRP/BNB no tradeados en run)
7. Observability gap: fills de brackets SL/TP no emiten lifecycle events (solo STOP_REQUESTED/ACCEPTED) — 6/7 cierres sin CLOSED event

## Decisión final (solo certifica el usuario)
- [ ] PASS → merge a main + tag v9.3.0-multi-coin-certified
- [ ] FAIL → fix + re-run
- [ ] PASS condicional → fix hallazgos 4/7 en dev + re-correr 12h gate

---

# Run v2 (Full Endurance 24h — interrumpido por hallazgo #8)

> **Fecha**: 2026-08-12 11:39 → 13:55 (abort INT, ~2h17m)
> **PID**: 9731 | **Log**: `/tmp/endurance_24h_v2.log`
> **Contexto**: validación de fixes 1-4 (v1) + nuevo patrón de error detectado al minuto 3

## Causa de interrupción (decisión usuario, 13:55)
- **Hallazgo #8**: `-4120` ×6 a los 3 minutos de arranque — brackets SOL (notional $14.47 < min $20) usaban `closePosition=True` + amount=0. Binance **rechaza condicionales (TP/SL MARKET) con closePosition en Main API** (-4120: "use the algo order api endpoints instead"), contradiciendo la suposición "Phase 248". ErrorHandler retry ×3 (ERROR spam) → fallback Algo API (reduceOnly + qty) → éxito ×2.
- Riesgo real: si `_get_position_size_for_algo_fallback` falla, el `raise` propaga → bracket nunca colocado → posición sin SL.
- 0 trades cerrados en las 2h → ninguna validación de fixes 1-4 en riesgo de perderse (todo el valor es de la corrida v3).

## Fix aplicado (Phase 248 Revision 2 — diseño)
1. `exchanges/connectors/binance/binance_native_connector.py`: regla de ruteo corregida — **condicionales (TP/SL/OCO) → SIEMPRE Algo API**; `closePosition=True` solo válido para MARKET/LIMIT planos (dust cleanup). Conversión proactiva closePosition → reduceOnly + qty (vía `_get_position_size_for_algo_fallback`); sin tamaño resoluble → Main API last-resort (red de seguridad -4120 se mantiene).
2. `croupier/components/oco_manager.py` (`_create_tp_order`/`_create_sl_order`): brackets small-notional ahora usan **quantity real + reduceOnly=True** (mismo path que brackets normales, probado ≤ min notional en v2), nunca closePosition.
- Tests nuevos: `tests/unit/exchanges/test_binance_routing.py` (5) + `tests/unit/croupier/test_oco_manager_closeposition.py` (3) → 8/8 PASS.
- Suite completa: 104/105 (único fallo `test_limit_resync.py::test_auto_resync_on_1021_error` = **pre-existente en HEAD 58d6565**, verificado con worktree limpio, no relacionado).
- Validate-all: L0 (A-E) 5/5 PASS, L1 exit-integration PASS, L2 decision_pipeline 25 traces PASS, L3.1 audit PASS (historian.db poblado). L6 param_optimizer --validate-only en background (lento).

## Criterios de éxito (v3, por validar)
- [ ] Error Recovery = $0.00 (0 error trades) ← CRÍTICO
- [ ] 0 crashes / RAM estable (<50% crecimiento)
- [ ] Event Integrity = 100% (0 `WS Event UNMATCHED`)
- [ ] API Stability = 100% (0 errores `-4120`) ← con fix Phase 248 R2
- [ ] Trade Flow Observability = 100% (CREATED→FILLED→RECON_*→CLOSED, con fixes 4+STOP_FILLED)
- [ ] Orphan Hygiene < 2% (con fix reconciliation -2011)
- [ ] Full Exit: tracker vacío tras `--close-on-exit`

## Run v3 (tras pre-flight)
- [x] Relanzado: PID 22755 | log `/tmp/endurance_24h_v3.log` | timeout 1440 (ETA 2026-08-13 15:04)
- [x] Arranque limpio verificado: 0 errores, timer OK, balance sesión 2919.65 USDT
- [x] **Primer bracket small-notional (Hallazgo #8) colocado SIN -4120**: SOL SHORT (0.1924, notional $14.47/$14.73) → TP 1000000165123563 + SL 1000000165123564 en 1 intento, 0 ERRORs, 0 retries — fix Phase 248 R2 validado en producción
