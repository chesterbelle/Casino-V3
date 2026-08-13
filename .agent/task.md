# Task: Re-run Gate 12h (1.4B.5) — Validar fixes Hallazgo #10

> **Protocolo**: `.agent/workflows/stress-test.md` Fase B.2 + memory.md Reglas 17/21/22/23/24
> **Contexto**: Full Endurance v3 falló criterios formales por hallazgo #10 (cadena de 4 eslabones: Airlock retry ciego→-4116, identidad dual→-2013, NameError amount→safety close, cascada contable). Fixeado en commit `4d556eb` (branch `dev-9.3-cleanup-and-stress`): Airlock grace period query-before-resend + identidad unificada + amount resuelto. Suite 113/113 PASS sin warnings.
> **Estado**: SIN LANZAR — esperando autorización del usuario (Regla 13/14).

## Configuración del run (cuando el usuario diga "sí")
- [ ] Pre-Flight B.0: `emergency_cleanup.py` → 0 pos / 0 órdenes (verificar) → `reset_data.py`
- [ ] Lanzar: `nohup .venv/bin/python main.py --run-type trade --mode demo --exchange binance --symbol LTCUSDT,SOLUSDT,AVAXUSDT --close-on-exit --timeout 720 > /tmp/endurance_gate12h_v4.log 2>&1 &`
- [ ] Verificar arranque limpio: 0 errores, 3 símbolos suscritos, timer "Stopping in 720 minutes"

## Criterios de éxito (gate 12h)
- [ ] 0 errores `-4116` (ClientOrderId duplicated) ← el fix A
- [ ] 0 errores `-2013` en recovery sin open-order scan fallback ← el fix B + scan
- [ ] 0 `Smart Healing Failed` / NameError ← el fix #11
- [ ] Error Recovery = $0.00 (0 error trades) ← CRÍTICO
- [ ] 0 crashes / RAM estable (% crecimiento < 50%)
- [ ] Event Integrity = 100% (0 `WS Event UNMATCHED`)
- [ ] Airlock Latency = 100% + 0 fallbacks locales tras grace period
- [ ] API Stability = 100% (0 errores `-4120`)
- [ ] Orphan Hygiene ≥ 98%
- [ ] Full Exit: tracker vacío tras `--close-on-exit`

## Monitoreo (mantener tabla por hora)
| Timestamp | Evento | Hallazgo |
|-----------|--------|----------|
| (pendiente) | | |

## Auditoría post-run
- [ ] `utils/audit_logs.py /tmp/endurance_gate12h_v4.log` → VERDICT PASS
- [ ] `utils/audit_trade_flow.py --db data/historian.db` → PASS
- [ ] Verificar en log: 0 -4116 / 0 -2013 / 0 NameError / 0 fallbacks locales Airlock
- [ ] Revisar Orphan Hygiene con el auditor post-fix (los -2011 de bracket-cleanup deben seguir clasificándose benignos)
- [ ] SESSION SUMMARY: Error Leakage $0.00

## Decisión (solo certifica el usuario)
- [ ] PASS → Full Endurance 24h (1.4B.5) con --timeout 1440
- [ ] FAIL → fix + re-run gate 12h
