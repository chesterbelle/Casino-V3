# ISSUE-001 — Sheriff: "LIQUIDATION" falso positivo en exit_reason

**Severidad**: 🟡 Minor (no afecta operativa ni dinero, solo reporting)
**Detectado en**: DG-2 (3 de 4 trades mal clasificados)
**Archivo**: `core/portfolio/position_tracker.py` — `handle_account_update()` líneas 792-834

---

## Descripción

El **Liquidation Sheriff** (Phase 78.2) detecta cierres externos vía `ACCOUNT_UPDATE`
cuando `position_amount = 0`. Al determinar el `exit_reason`, evalúa en este orden:

```python
# ORDEN ACTUAL (INCORRECTO)
1. if pos.liquidation_level > 0  → exit_reason = "LIQUIDATION"   ← siempre True
2. elif pos.tp_level > 0         → exit_reason = "TP (ACCOUNT_UPDATE)"
3. elif pos.sl_level > 0         → exit_reason = "SL (ACCOUNT_UPDATE)"
```

El problema: **todo position tiene `liquidation_level` calculado al abrir**
(`entry * (1 ± 1/leverage + 0.005)`), por lo que la condición 1 es siempre `True`
y los trades se etiquetan como "LIQUIDATION" antes de checar TP/SL.

La fase de refinamiento (líneas 820-834) intenta corregir comparando el precio de
mercado actual con los niveles `tp_level`/`sl_level`, pero en el momento en que el
Sheriff corre la posición ya está cerrada y el precio spot puede haber movido lejos
del nivel de cierre real → el refinamiento falla y "LIQUIDATION" queda como label.

---

## Evidencia en DG-2

```
13:17:13 | Trade Closed: 1550902403 | LIQUIDATION | Won: True | PnL: 0.14   ← TP real
19:16:18 | Trade Closed: 1551225422 | TP (ACCOUNT_UPDATE) | Won: True       ← correcto
23:01:11 | Trade Closed: 1554168902 | LIQUIDATION | Won: True | PnL: 0.21   ← TP/SL real
23:19:29 | Trade Closed: 1555648973 | LIQUIDATION | Won: False | PnL: -0.32 ← SL real
```

Solo 1 de 4 trades fue clasificado correctamente.

---

## Root Cause

```python
# position_tracker.py línea 793
if (
    pos.liquidation_level       # ← siempre existe
    and pos.liquidation_level > 0   # ← siempre True
    and pos.liquidation_level != pos.entry_price  # ← siempre True
):
    exit_price = pos.liquidation_level
    exit_reason = "LIQUIDATION"   # ← bloquea la detección de TP/SL
```

---

## Fix Propuesto

Invertir la prioridad: checar TP/SL vs entry_price PRIMERO, y usar LIQUIDATION
solo como fallback de último recurso cuando el precio de mercado esté cerca del
nivel de liquidación.

```python
# ORDEN CORRECTO
exit_reason = "EXTERNAL_CLOSE"
exit_price = pos.entry_price

# 1. Intentar refinar con precio de mercado real (más preciso)
try:
    market_price = await self.adapter.get_current_price(symbol)
    if market_price and market_price > 0:
        exit_price = float(market_price)
        if pos.side == "LONG":
            if pos.tp_level and exit_price >= pos.tp_level * 0.999:
                exit_reason = "TP (ACCOUNT_UPDATE)"
            elif pos.sl_level and exit_price <= pos.sl_level * 1.001:
                exit_reason = "SL (ACCOUNT_UPDATE)"
            elif pos.liquidation_level and exit_price <= pos.liquidation_level * 1.01:
                exit_reason = "LIQUIDATION"
        else:
            if pos.tp_level and exit_price <= pos.tp_level * 1.001:
                exit_reason = "TP (ACCOUNT_UPDATE)"
            elif pos.sl_level and exit_price >= pos.sl_level * 0.999:
                exit_reason = "SL (ACCOUNT_UPDATE)"
            elif pos.liquidation_level and exit_price >= pos.liquidation_level * 0.99:
                exit_reason = "LIQUIDATION"
except Exception as e:
    # Fallback estático: usar niveles guardados
    if pos.tp_level and pos.tp_level > 0:
        exit_reason = "TP (ACCOUNT_UPDATE)"
        exit_price = pos.tp_level
    elif pos.sl_level and pos.sl_level > 0:
        exit_reason = "SL (ACCOUNT_UPDATE)"
        exit_price = pos.sl_level
```

---

## Estado

- [ ] Fix implementado
- [ ] Verificado en DG-3 o B.3
