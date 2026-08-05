# ISSUE-002 — Fees = $0.00 en trades cerrados por el Liquidation Sheriff

**Severidad**: 🟡 Minor (no afecta operativa, distorsiona reporting de PnL neto)
**Detectado en**: DG-2 (los 4 trades reportaron `Fee: 0.0000`)
**Archivos**:
- `core/portfolio/position_tracker.py` — `handle_account_update()` línea 854
- `croupier/croupier.py` — `_deferred_fee_enrichment()` línea 1238

---

## Descripción

Todos los trades cerrados por el **Liquidation Sheriff** reportan `Fee (Entry+Exit): 0.0000`
en los logs y en el Historian DB.

---

## Root Cause

**Doble problema:**

### 1. Sheriff llama `confirm_close` con `fee=0.0` hardcodeado

```python
# position_tracker.py línea 848-855
await self.confirm_close(
    trade_id=pos.trade_id,
    exit_price=exit_price,
    exit_reason=exit_reason,
    pnl=pnl,
    fee=0.0,   # ← hardcodeado, nunca se obtiene la fee real
)
```

### 2. `_deferred_fee_enrichment` existe pero NUNCA se llama

El método `_deferred_fee_enrichment` en `croupier.py` (línea 1238) fue diseñado
para hacer un background fetch de fees post-cierre, pero ningún código lo invoca:

```bash
$ grep -rn "_deferred_fee_enrichment" .
croupier/croupier.py:1238:    async def _deferred_fee_enrichment(...)   # ← solo definición, 0 llamadas
```

En DG-1 el enrichment SÍ funcionó para el trade RECON_FORCE porque ese path
lo llama explícitamente. Pero el Sheriff nunca dispara el enrichment.

---

## Impacto

```
Trade 1550902403 | Fee: 0.0000  (fee real Binance Testnet: ~$0.012)
Trade 1551225422 | Fee: 0.0000
Trade 1554168902 | Fee: 0.0000
Trade 1555648973 | Fee: 0.0000

Balance exchange real: $3004.18 (sube $0.10)
PnL reportado bruto:   $0.14 + $0.23 + $0.21 - $0.32 = +$0.26
Diferencia ($0.16):    fees no capturadas + diferencia de precios de mercado
```

---

## Fix Propuesto

**En `handle_account_update` de `position_tracker.py`**, después de llamar
`confirm_close`, disparar el enrichment de fees si el croupier está disponible:

```python
await self.confirm_close(
    trade_id=pos.trade_id,
    exit_price=exit_price,
    exit_reason=exit_reason,
    pnl=pnl,
    fee=0.0,
)

# Deferred fee enrichment (Sheriff trades)
if hasattr(self, '_croupier') and self._croupier:
    task = asyncio.create_task(
        self._croupier._deferred_fee_enrichment(pos.trade_id, symbol, delay_sec=3.0)
    )
```

**Alternativa más limpia**: mover `_deferred_fee_enrichment` al `PositionTracker`
o hacer que `confirm_close` acepte un callback de enrichment.

---

## Estado

- [ ] Fix implementado
- [ ] Verificado en DG-3 o B.3
