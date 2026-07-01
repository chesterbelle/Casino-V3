# Memory — Casino V3

## Estado de Capas
- **Capa de Hierro** (decision engine) — ✅ Completa
- **Capa de Cristal** (optimización + auditoría) — ✅ Completa
- **Capa de Acero** (validación multi-temporal) — 🔄 En progreso

## Baseline actual
- **LTC**: Golden params optimizados. Audit edge confirmado +0.1144% Net Taker (daily 24h datasets)
- **Trade mode mensual mayo 2026**: +0.17%, 40.3% WR, 1.81 PF (primer monthly completo ✅)

## Manual Técnico & Gotchas
- **`backtest.py`**: El `except Exception` no captura `asyncio.CancelledError` (BaseException en Py3.14). Siempre usar `except BaseException` + flush antes de `os._exit()`.
- **VA_GATE en mensuales**: `va_integrity` se satura con `total_volume` acumulado del mes completo. Los setups de mean-reversion pueden quedar bloqueados. Es por diseño, no bug.
- **Monthly datasets**: ~500MB+ vs daily ~20-100MB. Tiempo de procesamiento ~35 min para monthly completo (vs minutos para daily).
- **Backtest con nohup**: Usar `nohup` + redirección de log para evitar que el tool timeout mate el proceso.

## 📍 Ruta Actual (Roadmap Vivo)
1. ✅ Fix silent crash backtest mensual
2. ✅ Trade mode LTC monthly mayo 2026 completado
3. ⏳ Trade mode LTC monthly marzo 2026
4. ⏳ Trade mode LTC monthly abril 2026
5. 🔜 Análisis comparativo de los 3 meses mensuales
6. 🔜 Audit multi-coin (84 datasets)
