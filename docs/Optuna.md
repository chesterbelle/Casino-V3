# Análisis de cluster_optimizer.py y PARAMETER_SPACE

He analizado el archivo `scripts/cluster_optimizer.py` para entender cómo se parametriza y separa el `PARAMETER_SPACE` al ajustar por escenario. Aquí están los hallazgos detallados y las observaciones sobre si los ajustes están afectando correctamente el funcionamiento.

## 1. Cómo se separa el PARAMETER_SPACE

El script utiliza el diccionario global `PARAMETER_SPACE` para definir todos los rangos de hiperparámetros (min, max, step). Cuando utilizas el argumento `--only <escenario>`, el script llama a la función `filter_parameter_space(only)` para aislar el espacio de búsqueda.

La lógica de filtrado hace lo siguiente:
- Busca claves que comiencen con `sensors.<escenario>` o `targets.<escenario>`.
- **Excepción manual:** Si el escenario es `trend_acceptance`, se inyecta manualmente la clave `guardians.l2_ratio_min_trend_acceptance`.

Esto significa que, en principio, el aislamiento por escenario (al usar `--only`) funciona correctamente extrayendo solo las variables pertinentes.

## 2. Hallazgos y Problemas Críticos en la Parametrización

Al revisar el código, encontré **dos problemas críticos** que están impidiendo que algunos ajustes y escenarios funcionen correctamente o se optimicen de verdad:

### A. `tactical_absorption` no se puede aislar
Aunque el diccionario `PARAMETER_SPACE` contiene parámetros para `tactical_absorption` (ej. `sensors.tactical_absorption.z_score_min`), el parser de argumentos bloquea su uso por escenario.
```python
# Línea 701
parser.add_argument(
    "--only",
    choices=["failed_breakout", "liquidity_exhaustion", "trend_acceptance"], # FAAAAALTA tactical_absorption
)
```
**Efecto:** Si intentas ejecutar `--only tactical_absorption`, el script arrojará un error porque no es una opción válida en `choices`. Solo se pueden ajustar sus parámetros corriendo una optimización global (sin `--only`).

### B. El Scoring Global (Multi-escenario) ignora `trend_acceptance` y `tactical_absorption`
En la función `compute_composite_score`, cuando se corre la optimización sin `--only` (multi-escenario), se evalúa un "composite score". Sin embargo, el cálculo de la esperanza matemática (expectancy) de las configuraciones teóricas **está hardcodeado para considerar solo dos escenarios**:
```python
# Línea 393
for setup, data in metrics.best_uniforms.items():
    if setup in ("failed_breakout", "liquidity_exhaustion"):
        fb_le_total += data["exp"] - FEE_TAKER_RT
        fb_le_count += 1
```
**Efecto:** Si optimizas de manera global (sin `--only`), el optimizador no premiará mejoras directas en la esperanza de `trend_acceptance` ni de `tactical_absorption`. Sus aportes solo se reflejarán vagamente en el `net_taker` total, haciendo que la optimización global esté sesgada hacia `failed_breakout` y `liquidity_exhaustion`.

## 3. Conclusión y Recomendaciones

Si estás ajustando por escenario usando `--only failed_breakout`, `--only liquidity_exhaustion` o `--only trend_acceptance`, **sí estás optimizando correctamente** (gracias a la lógica de `compute_composite_score` para `only is not None`).

Para corregir los problemas encontrados:

1. **Añadir `tactical_absorption` al CLI:**
   En la línea 701, modifica los choices para incluir `"tactical_absorption"`:
   ```python
   choices=["failed_breakout", "liquidity_exhaustion", "trend_acceptance", "tactical_absorption"]
   ```
2. **Arreglar el Scoring Global:**
   En la función `compute_composite_score`, cambia el condicional para incluir los demás setups si deseas que el optimizador global los tome en cuenta de forma equilibrada:
   ```python
   if setup in ("failed_breakout", "liquidity_exhaustion", "trend_acceptance", "tactical_absorption"):
   ```

Con estos cambios, la parametrización funcionará al 100% como se espera en todos los escenarios.
