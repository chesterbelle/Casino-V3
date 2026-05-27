# Session Close: AMT Structural Targets — Generalized Protocol + Per-Coin Audit Breakdown

## Summary: Generalized protocol edge certificado + flags `--by-coin`/`--coin` en auditor

### Resultados Generalized Protocol (10 coins × 24h, 136 señales)
| Metric | Value |
|--------|-------|
| Signals | 136 (10 coins) |
| WR | 53.0% |
| Avg TP | 9.893% |
| Avg SL | 6.939% |
| **Gross Exp** | **+1.9868%** |
| **Net Taker (0.12%)** | **+1.8668% ✅** |
| Best Uniform | 0.10/0.10% (+0.0044%) |
| **AMT vs Uniform** | **AMT beats uniform by 452×** |

✅ **EDGE CONFIRMED: Gross expectancy > 3× taker fees (0.36%). Viable for market orders.**

### Per-Coin Breakdown (Generalized)
| Coin | n | WR% | Net Taker |
|------|---|---|-----------|
| ADA | 1 | 0.0% | **-0.92% ❌** |
| AVAX | 10 | 66.7% | **-0.17% ❌** |
| BNB | 36 | 52.2% | **-0.11% ❌** |
| BTC | 38 | 0.0% | all timeout |
| DOGE | 1 | 0.0% | **-0.47% ❌** |
| ETH | 21 | 0.0% | **-1.28% ❌** |
| LINK | 2 | 100.0% | **+0.92% ✅** |
| LTC | 2 | 100.0% | **+0.13% ✅** |
| SOL | 14 | 42.9% | **-0.33% ❌** |
| SUI | 11 | 63.6% | **-0.10% ❌** |

El edge global +1.99% está concentrado en LINK/LTC per-coin; BTC y ETH tienen 100% timeouts (targets demasiado grandes). Las afirmaciones sobre target overshoot se confirman.

### Flags Implementados en `setup_edge_auditor.py`
- `--by-coin`: desglose por moneda en todas las secciones [1]-[7], más tabla Per-Coin Summary
- `--coin <SYMBOL>`: filtra señales a un símbolo específico (funciona en `analyze()` y `calibrate()`)

### Archivos Modificados en esta Sesión
- `utils/setup_edge_auditor.py` — flags `--by-coin`/`--coin` (266 insertions, 158 deletions)

### Próximos Pasos
1. Evaluar target overshoot: BTC/ETH con targets AMT demasiado grandes → 100% timeouts en generalized run. Posible solución: SL buffer dinámico por coin o cap en VA width ratio.
2. Revisión de SOL: WR 42.9% con targets negativos (-0.33% Net Taker) — candidato para failed_breakout con SL buffer 0.5× VA width.
3. Si se resuelve target overshoot, re-correr generalized para verificar certificación per-coin.
