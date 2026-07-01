# Changelog

## 2026-07-01 — Fix silent crash en backtest mensual + LTC trade mode monthly ✅

### Archivos modificados
- `backtest.py` — `except Exception` → `except BaseException` (no capturaba `asyncio.CancelledError` en Python 3.14); flush logs antes de `os._exit()`; exit codes correctos
- `decision/signal_arbitrator.py` (commit anterior) — pasar `context_registry` a `SignalArbitrator.__init__`

### Hallazgos y Errores
- **Bug crítico**: `backtest.py` moría silenciosamente en datasets grandes (monthly 500MB+). La excepción `asyncio.CancelledError` (subclase de `BaseException` en Python 3.14) no era capturada por `except Exception`. El `finally: os._exit(0)` mataba el proceso antes de que el logger flusheara el error.
- **Falsa alarma inicial**: Resultados parciales del monthly (92 trades, -17.13 USDT, 8.7% WR) eran de un backtest truncado. El monthly completo dio +0.17%, 40.3% WR, 1.81 PF.
- **VA_GATE**: En datasets mensuales `va_integrity` puede saturarse por acumulación de `total_volume`, bloqueando setups de mean-reversion. No invalida el edge — es esperado por diseño.

### Métricas LTC Monthly Trade — Mayo 2026
```
Final Balance    : $10,017.49
PnL Total        : +$17.49 (+0.17%)
Total Trades     : 149
Win Rate         : 40.3%
Profit Factor    : 1.81
Ledger Integrity : ✅ PASS

Señales dispatchadas: 300
  liquidity_exhaustion: 140 (46.7%)
  trend_acceptance    : 159 (53.0%)
  failed_breakout     :   1 ( 0.3%)
```

### Próximos pasos (próxima sesión)
1. Correr trade mode mensual LTC marzo y abril 2026
2. Analisis comparativo de resultados mensuales
