# Fast-Track Flag Analysis for Absorption V1

## Problema Identificado

El flag `--fast-track` está diseñado para **protocolos de validación de infraestructura** (ej. `/fast-track-parity`), bypasseando gates de calidad para forzar la ejecución de órdenes y testear el Event Loop bajo saturación.

**Estado actual:**
- ✅ LTA V4: `fast_track` bypasea 6 guardians (Regime, POC Migration, VA Integrity, Failed Auction, Delta Divergence, Spread Sanity)
- ❌ **Absorption V1: NO bypasea ningún gate** → Señales pueden ser rechazadas en fast-track mode

## Gates en AbsorptionSetupEngine que Bloquean Fast-Track

### 1. CVD Flattening Check (`_check_cvd_flattening`)
**Propósito:** Confirmar que el CVD slope está cerca de cero (absorption detuvo el movimiento)
**Threshold:** `abs(cvd_slope) < 5.0`
**Problema en fast-track:** Si no hay suficiente historial de CVD, el slope puede ser alto y rechazar la señal

### 2. Price Holding Check (`_check_price_holding`)
**Propósito:** Confirmar que el precio se mantiene cerca del nivel de absorption
**Threshold:** `distance_pct < 0.05%`
**Problema en fast-track:** En ventanas cortas (15-30 min), el precio puede moverse rápido y no "hold"

### 3. TP Distance Validation (`_calculate_tp`)
**Propósito:** Asegurar que el TP está entre 0.10% - 0.50%
**Threshold:** `0.10% <= tp_distance_pct <= 0.50%`
**Problema en fast-track:** Si el FootprintRegistry no tiene suficiente volumen profile, puede no encontrar LVN válido

## Impacto en Protocolos de Validación

### `/fast-track-parity` (30 min)
**Comando:** `main.py --mode demo --symbol LTC/USDT:USDT --timeout 30 --fast-track --close-on-exit`
**Propósito:** Verificar paridad mecánica Demo vs Backtest
**Impacto:** Absorption V1 puede generar 0 trades si:
- CVD slope > 5.0 (mercado trending)
- Precio se mueve > 0.05% del nivel de absorption
- No hay LVN en rango 0.10% - 0.50%

### `/execution-quality-audit` (15 min)
**Comando:** Similar a fast-track-parity
**Propósito:** Verificar pipeline asíncrono (zero stalls)
**Impacto:** Mismo problema, puede generar 0 trades

## Solución Propuesta

### Opción 1: Bypass Completo (Recomendada para Fast-Track)
Pasar `fast_track` flag al `AbsorptionSetupEngine` y bypassear las 3 confirmaciones:

```python
def __init__(self, fast_track: bool = False):
    self.fast_track = fast_track
    # ...

def _check_cvd_flattening(self, symbol: str) -> bool:
    if self.fast_track:
        return True  # Bypass for infrastructure validation
    # ... existing logic

def _check_price_holding(self, current_price: float, level: float, timestamp: float) -> bool:
    if self.fast_track:
        return True  # Bypass for infrastructure validation
    # ... existing logic

def _calculate_tp(self, symbol: str, absorption_level: float, direction: str, current_price: float) -> Optional[float]:
    if self.fast_track:
        # Mock TP at fixed distance (0.20%)
        if direction == "SELL_EXHAUSTION":
            return current_price * 1.002  # +0.20%
        else:
            return current_price * 0.998  # -0.20%
    # ... existing logic
```

### Opción 2: Bypass Selectivo (Más Conservador)
Solo bypassear CVD flattening y price holding, mantener TP distance validation:

```python
def _check_cvd_flattening(self, symbol: str) -> bool:
    if self.fast_track:
        return True
    # ... existing logic

def _check_price_holding(self, current_price: float, level: float, timestamp: float) -> bool:
    if self.fast_track:
        return True
    # ... existing logic

# TP distance validation se mantiene (asegura que el setup tiene sentido matemático)
```

### Opción 3: No Cambiar Nada (Más Seguro)
Mantener Absorption V1 sin bypass de fast-track. Consecuencias:
- ✅ Absorption V1 nunca opera en modo fast-track (más seguro)
- ❌ No se puede testear infraestructura de Absorption V1 con `/fast-track-parity`
- ❌ Protocolos de validación solo testean LTA V4

## Recomendación

**Opción 1 (Bypass Completo)** es la recomendada porque:
1. Mantiene consistencia con LTA V4 (todos los guardians bypasseados en fast-track)
2. Permite testear infraestructura de Absorption V1 con protocolos existentes
3. El flag `--fast-track` está claramente documentado como "NUNCA en producción"
4. Los gates de calidad defensiva (Math Inversion, PortfolioGuard, Min Notional) se mantienen activos

## Cambios Necesarios

### 1. `decision/absorption_setup_engine.py`
- Agregar `fast_track: bool = False` al `__init__`
- Agregar bypass en `_check_cvd_flattening`
- Agregar bypass en `_check_price_holding`
- Agregar mock TP en `_calculate_tp`

### 2. `decision/setup_engine.py`
- Pasar `self.fast_track` al `AbsorptionSetupEngine.__init__`

### 3. Documentación
- Actualizar `memory.md` con nota sobre fast-track bypass en Absorption V1
- Actualizar `.agent/workflows/fast-track-parity.md` (si existe)

## Riesgos

**Bajo riesgo** porque:
- Fast-track solo se usa en validación, nunca en producción
- Los gates defensivos críticos (Math Inversion, PortfolioGuard) se mantienen
- El bypass es explícito y documentado
- Absorption V1 está desactivado por defecto en config

## Próximos Pasos

1. Implementar Opción 1 (Bypass Completo)
2. Ejecutar `/fast-track-parity` con Absorption V1 activado
3. Verificar que genera trades (aunque sean sintéticos)
4. Actualizar documentación

---

**Fecha:** 2026-04-27
**Fase:** Phase 6 (Validation Updates)
**Status:** ANÁLISIS COMPLETADO, PENDIENTE IMPLEMENTACIÓN
