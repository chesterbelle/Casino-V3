# Propuesta: CVD Footprint como Capa Discriminativa para Thin Books

**Estado**: Pendiente — evaluar después de implementar z-scores auto-calibrados (v8.8).
**Autor**: Developer de confianza
**Fecha**: 2026-06-12

---

## 1. Problema que Resuelve

Los z-scores auto-calibrados normalizan la detección de absorción para que sea agnóstica a la microestructura del libro. Pero **normalizar no es lo mismo que discriminar**. En thin books (AVAX, DOGE, XRP), el ruido de alta frecuencia puede producir concentración anómala igual que la absorción real — el z-score no distingue entre "esto es raro" y "esto es institucional".

El CVD footprint añade una dimensión ortogonal: **intencionalidad sostenida en el flujo de órdenes**.

## 2. La Idea

Cuando un institucional acumula/esconde una orden en un book delgado, no la mete de golpe — la parte en tramos para no mover el precio. Esto crea un patrón distintivo en el Cumulative Volume Delta (CVD):

- El delta se vuelve **consistentemente positivo** (o negativo) durante ~10-30 segundos
- El **precio no se mueve proporcionalmente** (la absorción evita el slippage)
- El ruido aleatorio de minoristas oscila alrededor de cero sin dirección sostenida

**La huella (footprint)** se define como:

```
footprint_ratio = abs(CVD_acumulado_ventana) / abs(price_displacement_ventana)
```

- **High footprint** → mucho CVD movió poco precio → absorción real (intencionalidad)
- **Low footprint** → poco CVD o mucho desplazamiento → falso positivo (ruido o trend real)

## 3. Diseño de Implementación

### 3.1 En PressureEngine

Añadir un rolling buffer de CVD history para calcular acumulados por ventana:

```python
# Buffer circular de los últimos N segundos de CVD
self.cvd_window = deque(maxlen=window_size)
self.price_window = deque(maxlen=window_size)
```

En el loop de `update()`:

```python
# Acumular entradas con timestamp
self.cvd_window.append((timestamp, self.current_cvd))
self.price_window.append((timestamp, current_price))

# Calcular acumulados en ventana (ej: últimos 20 segundos)
window_start = timestamp - cvd_window_seconds
cvd_sum = sum(cvd for ts, cvd in self.cvd_window if ts >= window_start)
price_disp = abs(current_price - price_at_window_start)

if price_disp > 0 and cvd_sum != 0:
    footprint_ratio = abs(cvd_sum) / price_disp
else:
    footprint_ratio = 0.0
```

### 3.2 En PressureState

```python
@dataclass
class PressureState:
    # ... campos existentes ...
    cvd_footprint_ratio: float = 0.0  # NUEVO
```

### 3.3 En AbsorptionDetector

Usar el footprint como un filtro adicional después del z-score. No reemplaza — es un AND lógico:

```python
# Después del z-score absorption check
if state.absorption_score >= absorption_score_min:
    # Además, verificar footprint si el perfil lo requiere
    if min_footprint_ratio > 0 and state.cvd_footprint_ratio < min_footprint_ratio:
        return None  # Mucho ruido, poca intencionalidad
```

### 3.4 Parámetro Nuevo en coin_profiles

```python
"absorption_detector": {
    # ... params existentes ...
    "min_footprint_ratio": 0.0,  # 0 = desactivado. Thin books: ~2.5-5.0
}
```

Perfiles sugeridos:
- **SOL_INERTIAL_TRENDING**: `min_footprint_ratio: 0.0` (no necesita, el z-score + L2 gate funciona)
- **AVAX_NOISY_UNCERTAIN**: `min_footprint_ratio: 3.0` (necesita discriminación extra)
- **NOISY_UNCERTAIN_1**: `min_footprint_ratio: 2.5` (grupo heterogéneo, beneficio medio)
- **INERTIAL_TRENDING**: `min_footprint_ratio: 0.0` (ETH/LINK — similar a SOL)
- **NOISY_UNCERTAIN**: `min_footprint_ratio: 4.0` (NEAR — sin datos, perfil más estricto)

## 4. Riesgos y Mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Ventana arbitraria**: ¿20 segundos? ¿30? ¿10? | Parametrizar `cvd_window_seconds` con default 20s. Tunear por perfil igual que cooldown. |
| **Falsos negativos**: absorción real con precio moviéndose | El footprint es un filtro adicional, no un reemplazo. Si `min_footprint_ratio=0` está desactivado. |
| **Costo computacional**: buffer circular + sumas por ventana | O(n) por update, pero n = ~20-30 elementos con deque. Despreciable. |
| **Correlación con z-score**: ambos miden anomalía | Son ortogonales: z-score mide intensidad instantánea, footprint mide sostenibilidad temporal. |

## 5. Relación con Z-Scores Auto-Calibrados

No son competencia, son complementarios:

```
book_bucket_pct → concentration/noise coherentes
                        ↓
              RollingZScore → z_concentration / z_noise → absorption_score normalizado
                        ↓
              CVD footprint → discriminación intencionalidad → filtro adicional
                        ↓
              Señal T_ACC solo si ambos confirman
```

**El z-score responde "¿esto es anómalo para este libro?"**
**El CVD footprint responde "¿esto es intencional o es ruido?"**

Ambos necesarios para thin books. En books profundos (SOL), el z-score solo es suficiente porque el ruido de fondo ya es bajo.

## 6. Timeline Sugerido

| Paso | Dependencia |
|---|---|
| 1. Implementar z-scores auto-calibrados (v8.8) | — |
| 2. Validar edge en SOL/AVAX/XRP con z-scores | Paso 1 |
| 3. **Si edge sigue siendo negativo en AVAX → implementar CVD footprint** | Paso 2 |
| 4. A/B test con ambas capas activas | Paso 3 |
| 5. Si funciona → añadir parámetro a perfiles, limpiar legacy | Paso 4 |
