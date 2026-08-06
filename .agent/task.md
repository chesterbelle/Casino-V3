# Debug-Gate 12h — Ciclo de Depuración (Fase 1.4B.2)

> **Objetivo**: Obtener 2 runs consecutivos de 12h con Error Recovery = $0.00 antes de pasar a Full Endurance (24h).
> **Símbolo**: LTCUSDT | **Modo**: demo (Testnet)
> **Metodología**: Cada error encontrado → fix → re-correr desde Pre-Flight B.0.

---

## 📋 Checklist Pre-Flight (OBLIGATORIO antes de CADA run)

- [ ] `emergency_cleanup.py` ejecutado
- [ ] Verificación: 0 posiciones / 0 órdenes en exchange (assert pass)
- [ ] `reset_data.py` ejecutado
- [x] Branch activo: `dev-9.3-cleanup-and-stress`
- [x] Ejecutar Paso 1.4B.2a (DG-1: 12h LTCUSDT)
- [x] Analizar post-mortem DG-1 (encontrar bugs)
- [x] Ejecutar Paso 1.4B.2b (DG-2: 12h LTCUSDT)
- [x] Fix ISSUE-001 y ISSUE-002 (Sheriff)
- [/] Ejecutar Paso 1.4B.3 (DG-3: 12h Multi-Coin LTC, SOL, AVAX)
- [ ] Ejecutar Paso 1.4B.4 (24h Full Endurance)

---

## Errores Pendientes de Investigar

### ✅ Error -4120 — RESUELTO (commit `ec07d2a`)
- **Mensaje**: `"Order type not supported for this endpoint. use algo order api"`
- **Root cause**: `STOP_MARKET`/`TAKE_PROFIT_MARKET` con `closePosition=True` forzaban la main API (`/fapi/v1/order`), pero Binance Testnet ahora rechaza ese tipo en main API con -4120.
- **Fix** (`binance_native_connector.py`): Al detectar `-4120` en orden STOP, obtiene el tamaño real de posición via `fetch_positions()`, convierte `closePosition→reduceOnly + quantity>0`, y reintenta via Algo API (`/fapi/v1/algo/order`).
- **Estado**: ✅ Commiteado y listo para validar en el primer run de 12h.


---

## Runs del Debug-Gate

| Run | Duración objetivo | Inicio | Log | Resultado |
|-----|-------------------|--------|-----|-----------|
| **DG-1** | **12h** | **2026-08-03 23:18** | `logs/debug_gate_12h_20260803_231802.log` | 🟡 10h52min — PC reiniciado. 7h limpias, bugs emergieron a las 07:00 |
| **DG-2** | **12h** | **2026-08-04 12:25** | `logs/debug_gate_12h_20260804_122518_DG2.log` | 🟢 En curso |


> Una vez DG-2 limpio → revisar si se necesita DG-3 o pasar a **B.3 Full Endurance (24h)**.

---

## 🐛 Bugs encontrados en DG-1 y fixes aplicados

### ✅ Bug A — `original_sl_pct` UnboundLocalError en `oco_manager.py:restore_bracket()`
- **Cuándo**: A las 07:00:13, ExitEngine intentó modificar el SL → Smart Healing activado → path de precios absolutos → `original_sl_pct` referenciado antes de inicializar.
- **Fix** (`2a34cf6`): Inicializar `original_tp_pct = None` y `original_sl_pct = None` antes del bloque `if/else`. Logs usan `or 'abs'` como fallback.

### ✅ Bug B — `OpenPosition.__init__()` faltaba `timestamp` en `reconciliation_service.py:_assimilate_position()`
- **Cuándo**: Inmediatamente después de Bug A. ReconciliationService intentó adoptar la posición (heurística) → `OpenPosition` requiere `timestamp: float` (Phase 800, Grace Period) pero la llamada lo omitía → `TypeError`.
- **Fix** (`2a34cf6`): Calcular `entry_ts_float` desde el timestamp del exchange (ms→s), con fallback a `time.time()`, y pasar como `timestamp=entry_ts_float`.

---

## Historial de Runs Previos (referencia)

| Run | Inicio | Duración real | Resultado |
|-----|--------|--------------|-----------|
| 1 | 2026-07-29 11:57 | 24h | ✅ Completo (8 trades, leves bugs) |
| 2 | 2026-07-30 00:28 | 2.5h | ❌ Muerta (zombie) |
| 3 | 2026-07-30 11:31 | 24h | ✅ Completo (+0.46%, 8 trades) |
| 4 | 2026-07-30 21:07 | — | ❌ 237 TASK STALL (falsos) |
| 5 | 2026-07-31 01:26 | — | ❌ Flytest falló |
| 6 | 2026-07-31 01:45 | 7h | 🟡 Server restart (PASS parcial) |
| 7 (Mini-Endurance) | 2026-08-02 | 7h | ✅ Error Recovery=$0, Phase 1.4B.1 PASS |
| 8 | 2026-08-02 10:07 | ~8h | 🟡 Interrumpido — posición fantasma -1007 (445 errores) |
| 9 | 2026-08-03 07:23 | ~9h | 🟡 Interrumpido (kill manual) — posición fantasma heredada |
| 10 | 2026-08-03 20:58 | — | 🟡 Parado por sesión de discusión — 29 errores -4120 al arrancar |
