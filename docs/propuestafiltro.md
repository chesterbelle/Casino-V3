# Propuesta Técnica: Refactor del VA_GATE (Filtro de Régimen)

## 1. El Descubrimiento del Flaw Arquitectónico
Al inspeccionar el código de `signal_arbitrator.py`, he encontrado la causa exacta de por qué `trend_acceptance` dispara cientos de veces en falso durante el backtest mensual.

El código actual dice:
```python
threshold = va_gate.get("integrity_threshold", 0.15)

if va_integrity >= threshold:
    return candidates  # Regime healthy (RANGE), allow all

# Regime degraded (TRENDING) - apply selective filter
block_set = set(va_gate.get("block_in_trending", []))
```

**El error lógico:**
Cuando la integridad del Value Area es alta (`>= 0.15`), el mercado está en un claro régimen de **RANGO** (el valor se está aceptando dentro de los bordes). En este régimen, el código actual hace un `return candidates` y permite TODOS los setups.

Esto significa que `trend_acceptance` (que es un setup de breakout/tendencia) **se le permite operar libremente en un mercado de rango**. Sale del rango por un tick, el detector cree que hay tendencia, entra, e inmediatamente el precio hace mean-reversion hacia el POC. Es la definición exacta de un *fakeout*.

## 2. La Solución Propuesta (AMT Puro)
Según la Teoría de Subasta (AMT), debemos ser estrictamente binarios con los regímenes:

*   **Régimen de Rango (Integrity Alta):** Los bordes se respetan.
    *   ✅ **Permitir:** `failed_breakout`, `liquidity_exhaustion`, `tactical_absorption` (Estrategias de Mean-Reversion).
    *   ❌ **Bloquear:** `trend_acceptance` (Estrategias de Breakout).
*   **Régimen de Tendencia (Integrity Baja):** Los bordes fallan, el valor migra.
    *   ✅ **Permitir:** `trend_acceptance` (Continuación).
    *   ❌ **Bloquear:** Mean-Reversions.

### Cambios en el Código:
En `decision/signal_arbitrator.py`, reescribiremos `_apply_va_gate()` para que evalúe ambas listas desde la configuración del perfil:

```python
# 1. Obtener listas del perfil (default fallback)
block_in_trending = set(va_gate.get("block_in_trending", ["failed_breakout", "liquidity_exhaustion", "tactical_absorption"]))
block_in_range = set(va_gate.get("block_in_range", ["trend_acceptance"]))

# 2. Aplicar lógica estricta
if va_integrity >= threshold:
    # MODO RANGO
    filtered = [sig for sig in candidates if sig.get("scenario") not in block_in_range]
else:
    # MODO TENDENCIA
    filtered = [sig for sig in candidates if sig.get("scenario") not in block_in_trending]

return filtered
```

## 3. Cambios en Configuración (`clusters_fixed.json`)
Necesitaremos agregar la nueva llave `"block_in_range": ["trend_acceptance"]` a la configuración de `va_gate` de los perfiles en `decision/config/clusters_fixed.json`.

## 4. Impacto Esperado
1.  **Erradicación de Fakeouts:** `trend_acceptance` solo podrá disparar cuando el `va_integrity` esté destruido (mercado en transición o tendencia violenta).
2.  **Net Taker Rescatado:** Esos 146 disparos perdedores de TA en el mensual LTC deberían reducirse a 10-20 disparos reales en momentos de tendencia real.
3.  **Alineación AMT 100%:** El bot pasará de adivinar a aplicar correctamente los conceptos institucionales de migración de valor.

## Siguiente Paso
Si apruebas esta propuesta, implementaré los cambios en `signal_arbitrator.py` y `clusters_fixed.json`, y correremos de nuevo el Audit Mensual LTC para certificar la victoria definitiva de la capa de Cristal.
