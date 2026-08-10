# Full Endurance 24h — Certificación Formal (Fase 1.4B.4)

> **Objetivo**: Validación formal de 24h con multi-coin concurrente. Certificar la estabilidad del sistema bajo operación prolongada (>1 sesión de trading: Asia + Europa + US).
> **Símbolos**: LTCUSDT, SOLUSDT, AVAXUSDT | **Modo**: demo (Testnet)
> **Método**: Auto-stop por `--timeout 1440` (24h × 60min) con drain phase + SIGNAL_STOP graceful.

---

## 📋 Checklist Pre-Flight B.0 (OBLIGATORIO)

- [x] `emergency_cleanup.py` ejecutado (exchange a cero)
- [x] Verificación: 0 posiciones / 0 órdenes en exchange (assert pass)
- [x] `reset_data.py` ejecutado (estado local limpio)
- [x] WAL checkpoint cleanup (Regla 17 protocolo)
- [x] Branch activo: `dev-9.3-cleanup-and-stress`
- [x] **6 fixes aplicados** (commit `ffd5a9a` del usuario + 5 míos):
  - [x] `59aeaca` — fix(multi-coin): DG-3 findings
  - [x] `d3e09e9` — feat(orphan-recovery): two-layer design
  - [x] `00575f5` — fix(connector): fetch_open_orders List[str]
  - [x] `793c35e` — fix(execution): skip startup recon comma-joined
  - [x] `ffd5a9a` — fix(position_tracker): 4 critical fixes (manual)
  - [x] `29d987e` — **fix(execution): pre-entry notional validation** (previene -4120 bracket failures)

> **⚠️ PC RESTART detectado** (motivos no relacionados): proceso murió a las 08:57 (run había durado ~41min). Encontradas 2 posiciones fantasma en exchange (SOLUSDT short 0.2 @73.9, AVAXUSDT long 4.0 @6.481). Pre-Flight B.0 ejecutado limpiamente. WAL checkpoint aplicado. Listo para relanzar.

---

## 🛡️ Fixes de Capa de Acero Aplicados (Esta Sesión)

### Commit `29d987e` — Pre-Entry Notional Validation
**Problema**: Trade 4178299900 (SOL LONG) abrió con notional $15 < min $20. El fallback `closePosition=True` falló con `-4120 "order type not supported"`, dejando posición SIN BRACKETS 20 min.

**Solución**: En `OrderExecutor.execute_market_order()`:
- `projected_notional = amount * current_price` vs `adapter.get_min_notional()`
- Rechaza con `ValidationError` si notional < mínimo
- Skips `reduceOnly` y `closePosition` (cierres válidos)
- Fallback graceful: si adapter falla → warning + continúa

**Tests**: 17/17 pasan (5 nuevos para esta validación)

---

## 🎯 Criterios de éxito (Certificación)

- [ ] **Error Recovery = $0.00** (0 error trades) — CRÍTICO
- [ ] **OCO_ABORTs = 0** (validar Two-Layer design)
- [ ] **Orphan Hygiene = 100%** (validar check_pending_orphans)
- [ ] **0 crashes** durante las 24h
- [ ] **API Stability = 100%** (0 logs de error `(-4120)`)
- [ ] **Drift = $0.00** mantenido
- [ ] **RAM estable** (<50% crecimiento)
- [ ] **Proceso graceful shutdown** (Reason: TIMEOUT)

## 📊 Métricas objetivo vs DG-3R (baseline 12h)

| Métrica | DG-3R (12h) | Objetivo 24h |
|---------|-------------|--------------|
| Trades | 3 | 6-10 (muestra estadística) |
| OCO_ABORTs | 0 | 0 |
| Orphan Hygiene | 100% | 100% |
| Recon cycles | 722 | ~1400+ |
| Drift | $0.00 | $0.00 |
| WR | 0/3 | >0% (muestra n>5) |

---

## 🚀 Comando de lanzamiento

```bash
nohup .venv/bin/python main.py \
  --run-type trade \
  --mode demo \
  --exchange binance \
  --symbol LTCUSDT,SOLUSDT,AVAXUSDT \
  --close-on-exit \
  --timeout 1440 \
  > /tmp/endurance_24h_$(date +%Y%m%d_%H%M%S).log 2>&1 &
```

---

## 📝 Log esperado

`/tmp/endurance_24h_YYYYMMDD_HHMMSS.log` (~50MB+)

---

## 🩺 Monitoreo — **Run v2 ACTIVO (PID 15063)**

**Inicio**: 2026-08-07 13:13:20 | **Auto-stop**: 2026-08-08 13:13 (~1440 min)
**Estado actual**: ~10h+ elapsed (revisar `ps -p 15063`)

### Métricas observadas (a las ~9h09min):
- **Trades cerrados**: 11 (4W / 6L / 1 EXTERNAL_CLOSE) | **PnL**: -1.20 USDT
- **OCO_ABORTs**: 0 ✅ | **Orphan Hygiene**: 100% ✅ (0 orphans reales)
- **Recon cycles**: 565+ | **Drift**: $0.00 ✅
- **RAM**: estable ~200 MB RSS | **Errores críticos**: 0 (-1007, -4120, Traceback)
- **API Stability**: 100% ✅ (nuevos -4120 prevenidos por validación pre-entry)

### Próximo checkpoint: ~13h (15:13) → ~18h (20:13) → ~24h (13:13 next day)

- **Intervalo**: cada ~2-3h via bash sleep loop
- **Métricas clave**: errores, OCO_ABORTs, orphan recovery, drift, posiciones, trades, recon cycles
- **Alertas críticas**: -1007, -4120, Traceback, MASS DETACHMENT, 🚨

---

## 📦 Resultado esperado

- Run de 24h completas (1440 min) con `Reason: TIMEOUT`
- SESSION SUMMARY con métricas certificadas
- Apto para merge a `main` + tag `v9.3.0-multi-coin-certified`
