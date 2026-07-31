# Stress Test — 24h Post-Fixes (Ronda 2)

## Bugs corregidos (ronda actual)

### 🐛 Bug 1 (GRAVE) ✅ — PositionTracker no liberaba posición tras cierre externo
- **Fix**: `core/croupier/croupier.py:213` — Añadido `await self.position_tracker.handle_account_update(event.data)`

### 🐛 Bug 2 (HIGH) ✅ — `execute_limit_order()` llamado sin args
- **Fix**: `exchanges/connectors/binance/order_executor.py:617-629` — Pasados kwargs correctamente

### 🐛 Bug 3 (MEDIUM) ✅ — PnL como Unexplained Variance (Liquidation Sheriff)
- **Fix**: `core/portfolio/position_tracker.py:789-830` — Exit price usando niveles + fallback a `get_current_price()` via REST

### 🐛 Bug 4 (LOW) ✅ — Airlock cancelación sin order_id
- **Fix**: `exchanges/connectors/binance/binance_native_connector.py:1589,1741` — Guard `if not order_id/algo_id: return`

### 🐛 Bug 5 (MEDIUM) ✅ — Misma causa que Bug 3 (Liquidation Sheriff con entry_price=0)
- **Resolución**: Cubierto por el fix de Bug 3 + mejora (`get_current_price` REST)

### 🐛 Bug 6 (GRAVE) ✅ — Workers zombies + TASK STALL falso + Queue corrupted
- **6a:** Recrear `multiprocessing.Queue` en cada restart de shard (`_start_market_data_stream:1863-1875`)
- **6b:** Exponencial backoff en health check restart del WS (`ensure_websocket:2543+`)
- **6c:** Cancelar subscription worker task vieja antes de respawn (evitar acumulación)
- **6d:** `put_nowait` en vez de `put()` bloqueante (línea 2162)

### 🐛 Bug 7 (MEDIUM) ✅ — Shutdown zombie (flytest fallido) en main.py:548-550
- **Fix:** Reemplazado `return` por terminate explícito de workers/exec/sensor + `os._exit(1)` (mismo patrón del finally)

## Runs

| Run | PID | Inicio | Log | Resultado |
|-----|-----|--------|-----|-----------|
| 1 | 41096 | 2026-07-29 11:57 | `logs/endurance_24h_20260729_115722.log` | ✅ 24h completo (8 trades, -4.11 USDT, leves bugs) |
| 2 | 16013 | 2026-07-30 00:28 | `logs/endurance_24h_20260730_002824.log` | ❌ Muerta a las 2.5h (zombie) |
| 3 | 28176 | 2026-07-30 11:31 | `logs/endurance_24h_20260730_113101.log` | ✅ 24h completo (+0.46%, 8 trades) |
| 4 | 6150 | 2026-07-30 21:07 | `logs/endurance_24h_20260730_210744.log` | ❌ Matada — 237 TASK STALL (falsos), workers zombie |
| 5 | 105241 | 2026-07-31 01:26 | `logs/endurance_24h_20260731_012639.log` | ❌ Flytest falló (workers lentos), shutdown colgado |
| **6** | **106756** | **2026-07-31 01:45** | **`logs/repro_run.log`** | **🟡 Matada (Server Restart) a las 7h (08:35). 1 Trade, 0 Zombies, PASS parcial.** |

## Run 6 — Resultado Parcial (Server Restart)
- **PID**: 106756 (Muerta por reinicio del servidor a las 08:35)
- **Duración**: ~7 horas
- **Auditoría (`utils/audit_logs.py`)**:
  - 1 Actual Trade
  - 0 Ghost Removals
  - 0 Unmatched Events
  - 19 errores `-2011` (cancelaciones inofensivas)
  - VERDICT: **PASS (Stable & Efficient)**
- **Zombies/Task Stalls**: 0 reportados antes de morir. Todo el fix de los bugs 1-7 parece haber funcionado perfecto.
