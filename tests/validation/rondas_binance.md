# Rondas de Validación - Binance

Este documento describe las 3 rondas de validación para el sistema de trading en Binance Testnet.

## 🎯 Objetivo

Validar que el sistema produce resultados consistentes entre:
- **Modo Demo** (trading en vivo en testnet)
- **Modo Backtest** (simulación con datos históricos)

## 📊 Configuración de Rondas

### Ronda 1: Detección Rápida (10 velas)

**Propósito**: Validación rápida para detectar problemas obvios

| Parámetro | Valor |
|-----------|-------|
| **Velas** | 10 |
| **Tiempo Esperado** | ~10 minutos |
| **Timeout** | 12.5 minutos (125% del tiempo esperado) |
| **Exchange** | Binance Testnet |
| **Symbol** | LTC/USDT:USDT |
| **Interval** | 1m |
| **Player** | Paroli |
| **Script** | `tests/validation/run_ronda1_binance.sh` |

**Comando**:
```bash
./tests/validation/run_ronda1_binance.sh
```

---

### Ronda 2: Validación Media (30 velas)

**Propósito**: Validación intermedia con más datos

| Parámetro | Valor |
|-----------|-------|
| **Velas** | 30 |
| **Tiempo Esperado** | ~30 minutos |
| **Timeout** | 37.5 minutos (125% del tiempo esperado) |
| **Exchange** | Binance Testnet |
| **Symbol** | LTC/USDT:USDT |
| **Interval** | 1m |
| **Player** | Paroli |
| **Script** | `tests/validation/run_ronda2_binance.sh` |

**Comando**:
```bash
./tests/validation/run_ronda2_binance.sh
```

---

### Ronda 3: Validación Completa (120 velas)

**Propósito**: Validación exhaustiva con dataset significativo

| Parámetro | Valor |
|-----------|-------|
| **Velas** | 120 |
| **Tiempo Esperado** | ~120 minutos (2 horas) |
| **Timeout** | 150 minutos (2.5 horas, 125% del tiempo esperado) |
| **Exchange** | Binance Testnet |
| **Symbol** | LTC/USDT:USDT |
| **Interval** | 1m |
| **Player** | Paroli |
| **Script** | `tests/validation/run_ronda3_binance.sh` |

**Comando**:
```bash
./tests/validation/run_ronda3_binance.sh
```

---

## ⏱️ Sistema de Timeout

Para prevenir que los scripts se queden esperando indefinidamente por velas que no llegan del exchange, se implementó un **timeout global**:

### Cálculo del Timeout

```
timeout_minutes = max_candles * 1.25
```

Esto permite un **25% de margen** para delays normales del exchange, pero evita esperas indefinidas.

### Comportamiento

- ✅ **Si se procesan todas las velas antes del timeout**: El script termina normalmente
- ⏱️ **Si se alcanza el timeout**: El script termina con las velas que haya procesado hasta ese momento
- 📊 **Logging**: El sistema registra cuántas velas se procesaron y el tiempo transcurrido

### Ejemplo

Para Ronda 3 (120 velas):
- **Tiempo esperado**: 120 minutos
- **Timeout configurado**: 150 minutos
- **Margen de tolerancia**: 30 minutos extra (25%)

---

## 📈 Métricas de Validación

Cada ronda compara las siguientes métricas entre Demo y Backtest:

| Métrica | Tolerancia | Descripción |
|---------|-----------|-------------|
| **Balance Final** | ±0.5% | Debe ser casi idéntico |
| **PnL Total** | ±1.0% | Diferencia aceptable en ganancias/pérdidas |
| **Número de Trades** | ±1 trade | Debe ejecutar los mismos trades |
| **Win Rate** | ±5.0% | Porcentaje de trades ganadores |
| **Win/Loss Count** | Exacto | Debe coincidir exactamente |

### Criterios de Éxito

Una ronda se considera **EXITOSA** si:
- ✅ Balance final dentro de tolerancia
- ✅ Número de trades coincide
- ✅ Win/Loss count coincide
- ✅ Win rate dentro de tolerancia

Una ronda se considera **FALLIDA** si:
- ❌ PnL fuera de tolerancia (aunque otras métricas pasen)
- ❌ Número de trades no coincide
- ❌ Win/Loss count no coincide

---

## 🔄 Flujo de Ejecución

Cada script de ronda ejecuta los siguientes pasos:

1. **Demo Trading**
   - Ejecuta `main.py` en modo demo
   - Procesa velas en tiempo real del exchange
   - Guarda resultados en `logs/demo_*.json`
   - Registra timestamps de todas las velas procesadas

2. **Descarga de Datos Históricos**
   - Extrae el rango de timestamps del demo log
   - Descarga datos históricos de Binance para ese rango exacto
   - Filtra el CSV para incluir solo las velas que el demo procesó
   - Guarda en `data/validation/historical_ronda*.csv`

3. **Backtest**
   - Ejecuta `main.py` en modo backtest
   - Usa el CSV filtrado con las mismas velas
   - Usa el mismo balance inicial que el demo
   - Guarda resultados en `logs/backtest_*.json`

4. **Comparación**
   - Ejecuta `compare_results.py`
   - Compara todas las métricas
   - Genera reporte en `logs/comparison_ronda*.txt`
   - Indica si la validación pasó o falló

---

## 📝 Archivos Generados

Cada ronda genera los siguientes archivos:

```
logs/
├── demo_YYYYMMDD_HHMMSS.json          # Resultados del demo
├── backtest_YYYYMMDD_HHMMSS.json      # Resultados del backtest
└── comparison_ronda*.txt               # Reporte de comparación

data/validation/
└── historical_ronda*.csv               # Datos históricos descargados
```

---

## 🐛 Troubleshooting

### El script toma mucho más tiempo del esperado

**Causa**: El exchange puede tener delays en el envío de velas.

**Solución**: El sistema tiene un timeout automático. Si el timeout se alcanza, revisa:
- Conexión a internet
- Estado del Binance Testnet
- Logs para ver cuántas velas se procesaron

### PnL no coincide entre Demo y Backtest

**Causa**: Diferencias en fees, slippage, o timing de ejecución.

**Estado**: Este es un problema conocido. Las diferencias absolutas son pequeñas ($0.10-$0.50) pero los porcentajes son altos porque los valores están cerca de cero.

**Próximos pasos**: Investigación en curso para reducir la discrepancia.

### Órden huérfana detectada

**Causa**: Órdenes TP/SL que no se cancelaron correctamente.

**Solución**: Implementado fix en `Croupier._cancel_sibling_order()` para ser más robusto ante errores del exchange.

---

## 📊 Resultados Históricos

### Ronda 1 (10 velas)
- ✅ Balance: Match
- ✅ Trades: Match
- ✅ Win/Loss: Match
- ❌ PnL: ~200% discrepancy

### Ronda 2 (30 velas)
- ✅ Balance: Match
- ✅ Trades: Match
- ✅ Win/Loss: Match
- ❌ PnL: ~396% discrepancy

### Ronda 3 (120 velas)
- ✅ Balance: Match (0.01% diff)
- ✅ Trades: Match (1 vs 1)
- ✅ Win/Loss: Match (0W/1L)
- ❌ PnL: ~3438% discrepancy ($0.42 absolute)

---

## 🔧 Configuración Técnica

### Fees Implementados

El backtest usa fees realistas:
- **Maker Fee**: 0.02% (0.0002)
- **Taker Fee**: 0.04% (0.0004)

### Timeout Implementation

Implementado en `core/data_sources/testing.py`:
- Parámetro: `max_wait_minutes`
- Cálculo automático en `main.py`: `int(max_candles * 1.25)`
- Verificación en cada iteración del loop de velas
- Logging cuando se alcanza el timeout

---

## 📚 Referencias

- [README.md](./README.md) - Documentación general de validación
- [compare_results.py](./compare_results.py) - Script de comparación
- [download_historical_data.py](./download_historical_data.py) - Script de descarga
