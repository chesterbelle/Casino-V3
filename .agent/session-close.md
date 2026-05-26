# Session Close: AMT Structural Targets — Full Long-Range Validation (v8.3-optimized)

## Summary: Replace ATR-multiplier targets with AMT geometric targets per setup
Implementados targets dinámicos basados en Auction Market Theory (POC, VAH, VAL) en todos los setups de reversion (`TacticalAbsorptionV2`, `absorption_reversal`, `failed_breakout`, `liquidity_exhaustion`), eliminando los multiplicadores ATR hardcodeados. Validado con long-range protocol (9 LTC datasets, 38 señales).

### AMT Target Design
Cada setup tiene su propia fórmula geométrica derivada de la posición del entry dentro del Value Area:

| Setup | Entry Zone | TP Target | SL (beyond entry boundary) |
|---|---|---|---|
| **TacticalAbsorptionV2** | IN_VALUE | Opposite VA boundary (VAH/ VAL) | -0.3×VA width |
| **absorption_reversal** | AT boundary / IN_VALUE | POC (center of value) | -0.3×VA width |
| **failed_breakout** | AT VA boundary re-entry | Opposite boundary | -0.5×VA width |
| **liquidity_exhaustion** | AT boundary bounce | Opposite boundary | -0.3×VA width |

Fallback: classic ATR multipliers si AMT data no está disponible o la geometría es inválida.

### Resultados Long-Range (9 LTC datasets)
| Metric | Before (ATR 5.0x) | After (AMT Structural) |
|---|---|---|
| Signals | 41 | 38 |
| WR | 36.6% | **66.7%** |
| MFE/MAE Ratio | 0.54 | **2.25** |
| Avg TP | 0.778% | **2.683%** |
| Avg SL | 0.518% | **2.953%** |
| Gross Exp | +0.0205% | **+0.8044%** |
| Net Taker (0.12%) | -0.0995% ❌ | **+0.6844% ✅** |
| Best Uniform | 0.80/0.80% (+0.0444%) | **AMT beats uniform by 18×** |

✅ **EDGE CONFIRMED: Gross expectancy > 3× taker fees (0.36%). Viable for market orders.**

### Archivos Modificados en esta Sesión
- `decision/setup_engine.py` — `_calculate_targets()` reemplazado: AMT structural (POC/VAH/VAL) para todos los setups, noise floor mínimo ATR-based, fallback ATR clásico cuando AMT no disponible

### Archivos Pendientes de Sesiones Anteriores (incluidos en este commit)
- `core/backtest_feed.py` — Fixes post-optimización
- `core/context_registry.py` — VWAP std O(1) residual fix
- `core/execution.py` — Fixes post-optimización
- `core/execution_process.py` — Fixes post-optimización
- `core/portfolio/portfolio_guard.py` — Fixes post-optimización
- `core/portfolio/position_tracker.py` — Fixes post-optimización
- `core/sensor_worker.py` — Fixes post-optimización
- `croupier/components/slim_exit_engine.py` — Fixes post-optimización
- `croupier/croupier.py` — Fix self.clock → time.time (Validate-All session)
- `scripts/orchestrator.py` — Restauración PROTOCOLS, clean_temp_data() historian.db (Validate-All + AMT)
- `utils/merge_historian.py` — Schema fix decision_traces
- `utils/setup_edge_auditor.py` — Fallback tp_pct/sl_pct
- `utils/validators/exit_engine_validator.py` — Fixes post-optimización
- `pyproject.toml` — aiosqlite dependency

### Próximos Pasos
1. Ejecutar generalized protocol (10 coins) para certificación multi-activo
2. Verificar performance en trend_acceptance (continuation, no reversion — pendiente de implementación AMT)
3. Evaluar si los SL buffers (0.3×/0.5× VA width) necesitan ajuste por setup

---
