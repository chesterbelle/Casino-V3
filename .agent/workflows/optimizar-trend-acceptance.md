# Protocolo de Optimización: Trend Acceptance (LTC)

El Edge Auditor determinó un `ENTRY FAILURE` para el escenario `trend_acceptance` en LTC. Esto significa que los filtros actuales de entrada están dejando pasar señales sin impulso direccional, y ningún ajuste de Take Profit / Stop Loss (por sí solo) puede hacer que la estrategia sea rentable.

Para solucionarlo, utilizaremos el motor de optimización bayesiana (Optuna) incluido en `scripts/cluster_optimizer.py`. Este script buscará matemáticamente la combinación ideal de filtros de entrada (L2 Ratio, CVD, etc.) que maximice el Net Taker.

## Paso 1: Ejecutar la Optimización (Solo TA)

Dado que solo `trend_acceptance` está perdiendo dinero de forma estructural, usaremos el flag `--only trend_acceptance` para que Optuna reduzca el espacio de búsqueda (PARAMETER_SPACE) exclusivamente a los parámetros de ese escenario, acelerando enormemente la convergencia.

**Comando sugerido:**
```bash
PYTHONUNBUFFERED=1 .venv/bin/python scripts/cluster_optimizer.py \
  --cluster LTC_NOISY_UNCERTAIN_1 \
  --coin LTCUSDT \
  --only trend_acceptance \
  --iterations 50 \
  --study-db data/db_vault/ltc_ta_study.db \
  > logs/optimizer_ltc_ta.log 2>&1
```

> **Nota:** Usar `--study-db` nos permite pausar y reanudar (`--resume`) el estudio en caso de que 50 iteraciones no sean suficientes para encontrar un Net Taker positivo, sin perder el progreso.

## Paso 2: Análisis de Sensibilidad y Selección

Una vez que el optimizador finalice, imprimirá un reporte en consola y guardará los resultados.
Debemos buscar específicamente la sección `BEST PARAMETERS FOUND` en el log.

El optimizador nos entregará los valores óptimos para:
- `ta_cvd_confirmation_threshold`
- `ta_l2_ratio_min`
- `ta_min_trade_distance`
- Entre otros filtros específicos del setup.

## Paso 3: Aplicar Parámetros y Validar

1. Copiar los valores generados por Optuna en la sección de `LTC_NOISY_UNCERTAIN_1` dentro de `config/coin_profiles.py`.
2. Correr de nuevo el **Backtest Runner** en modo auditoría para confirmar que, con los nuevos parámetros, `trend_acceptance` alcanza un **Net Taker positivo**.

```bash
.venv/bin/python scripts/backtest_runner.py --mode audit --symbol LTCUSDT --dataset-dir data/datasets/monthly_backtest_ready
```
