# Análisis Forense: Contaminación de Indicadores en Datasets Mensuales

## 1. Resumen del Problema

El backtesting sobre datasets mensuales (30 días continuos de trades concatenados)
produce resultados radicalmente distintos al backtesting sobre datasets diarios (24h
aisladas), a pesar de contener la misma data subyacente. El sistema se comporta como
si tuviera edge en 24h, pero pierde estrepitosamente en 30 días.

## 2. Diseño Experimental

### 2.1 Datasets Utilizados

| Conjunto | Tipo | Formato | Período |
|----------|------|---------|---------|
| 6 datasets LTC 24h | Diario aislado | `daily_backtest_ready/` | 2023-2025 |
| 4 TEST days | Días extraídos del monthly | `daily_backtest_ready/` | Mayo 2026 (días 1, 10, 15, 20) |
| 3 datasets mensuales LTC | Mensual continuo | `monthly_backtest_ready/` | Mar-May 2026 |

Los 4 TEST days fueron extraídos quirúrgicamente del monthly de Mayo 2026:
se copió el dataset completo y se eliminaron todas las filas fuera del rango
del día objetivo. El contenido de trades, depth snapshots y price candles para
ese día es idéntico al que existe dentro del mensual concatenado.

### 2.2 Condiciones de Prueba

- Perfil asignado: `LTC_NOISY_UNCERTAIN_1` (corregido — ver sección 5)
- Threshold L2 para trend_acceptance: 1.2
- Modo: audit (sin ejecución real, solo captura de señales)
- Símbolo: LTCUSDT
- Ventana de edge: 21600s (6h)

### 2.3 Datos Contaminados Previos

Antes del fix de perfiles, LTC se asignaba a `NOISY_UNCERTAIN_1` (threshold 2.0)
por un bug en `clusters_fixed.json` (formato de símbolos). Todos los datos
presentados en este documento usan el perfil correcto.

## 3. Evidencia: Discrepancia Daily vs Monthly

### 3.1 Señales Totales

| Métrica | Daily (10 datasets) | Monthly (3 datasets) | Δ |
|---------|--------------------|---------------------|---|
| Señales totales | 119 | 205 | +72% |
| trend_acceptance | 36 | 119 | +230% |
| failed_breakout | 10 | 57 | +470% |
| tactical_absorption | 52 | 21 | -60% |
| liquidity_exhaustion | 21 | 8 | -62% |

Los datasets mensuales generan significativamente más señales de trend_acceptance
y failed_breakout que los diarios aislados.

### 3.2 Net Taker por Setup

| Setup | Daily Net Taker | Monthly Net Taker | Degradación |
|-------|----------------|-------------------|-------------|
| **Overall** | **+0.1915%** | **-0.4754%** | **-0.67%** |
| trend_acceptance | +0.1277% | -0.6970% | -0.82% |
| failed_breakout | +0.1700% | -0.2770% | -0.45% |
| tactical_absorption | +0.1492% | -0.1557% | -0.30% |
| liquidity_exhaustion | +0.4157% | +0.5675% | +0.15% |

Tres de cuatro setups pasan de tener edge positivo en daily a tenerlo negativo
en monthly. Solo liquidity_exhaustion se mantiene positivo.

### 3.3 Win Rate y Calidad de Señal

| Setup | Daily WR | Monthly WR | Δ WR |
|-------|----------|-----------|------|
| trend_acceptance | 58.3% | 15.1% | -43.2 pp |
| failed_breakout | 80.0% | 45.6% | -34.4 pp |
| tactical_absorption | 34.6% | 14.3% | -20.3 pp |
| liquidity_exhaustion | 52.4% | 62.5% | +10.1 pp |

El win rate de trend_acceptance colapsa de 58.3% a 15.1% en el entorno mensual.

### 3.4 Entry Quality (Static Grid)

| Setup | Daily Entry OK | Monthly Entry OK | Cambio |
|-------|---------------|-----------------|--------|
| trend_acceptance | ✅ TARGETS OK (Exp +0.1977%) | ❌ ENTRY FAILURE (Exp -0.0608%) | Degradación total |
| failed_breakout | ✅ TARGETS OK (Exp +0.2400%) | ❌ ENTRY FAILURE (Exp -0.0735%) | Degradación total |
| tactical_absorption | ✅ TARGETS OK (Exp +0.2192%) | ❌ ENTRY FAILURE (Exp -0.0843%) | Degradación total |
| liquidity_exhaustion | ✅ TARGETS OK (Exp +0.5398%) | ✅ TARGETS OK (Exp +1.0690%) | Sin cambio |

En daily, todos los setups tienen entrada válida (el static grid encuentra
combinaciones TP/SL con expectancy positiva). En monthly, solo liquidity_exhaustion
mantiene entrada válida.

### 3.5 Proximidad de Targets (MFE vs TP)

| Setup | Daily Avg Prox | Monthly Avg Prox | Δ |
|-------|---------------|-----------------|---|
| trend_acceptance | 0.84 | 0.63 | -0.21 |
| tactical_absorption | 0.77 | 0.88 | +0.11 |
| failed_breakout | 0.95 | 0.87 | -0.08 |
| liquidity_exhaustion | 0.82 | 0.99 | +0.17 |

La proximidad de trend_acceptance cae en monthly: el precio se acerca menos
al target, indicando que las entradas apuntan en dirección incorrecta.

## 4. Test de Aislamiento (TEST Days)

### 4.1 Diseño

Se extrajeron 4 días específicos del monthly de Mayo 2026 (días 1, 10, 15, 20)
como datasets independientes. Cada TEST day contiene exactamente los mismos
trades, snapshots y candles que esa misma fecha dentro del mensual completo.

### 4.2 Señales en TEST Days vs Monthly

| Día | TEST day aislado (señales) | Misma fecha en monthly (señales) |
|-----|---------------------------|----------------------------------|
| Mayo 1 | 0 trend_acceptance | ~4 trend_acceptance |
| Mayo 10 | 0 trend_acceptance | ~4 trend_acceptance |
| Mayo 15 | 0 trend_acceptance | ~4 trend_acceptance |
| Mayo 20 | 0 trend_acceptance | ~4 trend_acceptance |

En el monthly, trend_acceptance genera señales los días 1, 10, 15 y 20.
En los TEST days aislados, trend_acceptance genera CERO señales esos mismos días.

La diferencia: en el monthly, los indicadores (CVD, VWAP, MarketProfile) llevan
días acumulándose antes de llegar a esos días. En el TEST day aislado, arrancan
de cero a las 00:00 UTC.

### 4.3 L2 Depth

| Dataset | Avg L2 Volume (bids+asks) |
|---------|--------------------------|
| 2024-05-01 daily | 2,885 |
| 2026-05 monthly | 7,123 |

El monthly tiene 2.5× más profundidad L2, pero las señales que genera son de
peor calidad. La profundidad L2 no es el factor determinante.

## 5. Nota: Bug de Perfiles Encontrado Durante la Investigación

Se descubrió que `config/clusters_fixed.json` almacenaba los símbolos en formato
`LTC/USDT:USDT`, mientras que los datasets usan `LTCUSDT`. El lookup estático
nunca matcheaba, y el fallback runtime usaba dimensiones de centroide
(`eff_abs`, `vel_rev`, `pers_brk`) que no coincidían con las métricas runtime
(`spread_ratio`, `depth_ratio`, `speed`). Esto causaba que **ninguna moneda**
recibiera su perfil correcto — todas caían a `NOISY_UNCERTAIN_1`.

Este bug fue corregido antes de generar los datos de este análisis (ver commit
en `feat-profile-fix`). Todos los datos presentados usan el perfil correcto.

## 6. Hipótesis Validada

La evidencia muestra que la concatenación de días en datasets mensuales permite
que los indicadores de estado (MarketProfile rolling window, CVD acumulado,
bandas VWAP, detectores de pullback) mantengan valores residuales entre días.
Esto genera tres efectos observables:

1. **Hiperactividad**: trend_acceptance produce 3.3× más señales en monthly que
   en daily aislado (119 vs 36).
2. **Falsos positivos**: Las señales adicionales tienen win rate drásticamente
   menor (15.1% vs 58.3%), indicando que el estado residual de los indicadores
   crea patrones que no representan oportunidades reales.
3. **Degradación de entrada**: El static grid no encuentra combinaciones TP/SL
   viables para 3 de 4 setups en monthly, mientras que en daily los 4 tienen
   entrada válida.

El rolling window de 8h en MarketProfile no es suficiente para eliminar el
estado residual cuando el flujo de datos es continuo durante 30 días. Los
indicadores construidos sobre ventanas móviles (rolling VWAP, CVD con
decaimiento, perfil de volumen) arrastran información de días anteriores que
contamina la lectura del régimen actual.

---

*Documento generado el 2026-07-02. Datos extraídos de backtest_runner audit mode
sobre LTCUSDT con perfil LTC_NOISY_UNCERTAIN_1.*
