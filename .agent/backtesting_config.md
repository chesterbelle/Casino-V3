# 📊 Configuración de Backtesting de Alta Fidelidad (Phase 1300)

Este documento detalla la infraestructura centralizada de datos L2 y Trades para Casino-V3, diseñada para eliminar la dependencia de CSVs y garantizar paridad determinista.

---

## 🏗️ Arquitectura de Datos

El sistema separa los datos en dos capas para evitar borrados accidentales durante auditorías:

1.  **Raw Data (`data/datasets/raw/`)**: Archivos originales `.csv.gz` descargados de Tardis o Binance.
2.  **Backtest Ready (`data/datasets/daily_daily_backtest_ready/`)**: Archivos `.db` (SQLite) procesados, listos para la simulación.

---

## 📊 Paso 0: Análisis de Precios Históricos

Antes de descargar datasets, usa el analizador para identificar qué meses tienen
condiciones de mercado variadas (TREND_UP, TREND_DOWN, BALANCE).

### Comando para analizar:
```bash
.venv/bin/python utils/data/price_history_analyzer.py --symbol <SYM> --months 24
```

### Comando para recomendar fechas:
```bash
.venv/bin/python utils/data/price_history_analyzer.py --symbol <SYM> --recommend
```

### Clasificación por condición (diaria, 1h klines):
*   **TREND_UP** 🟢: Ganancia >4% en el día, direction_ratio > 0.55
*   **TREND_DOWN** 🔴: Pérdida < -4% en el día, direction_ratio > 0.55
*   **BALANCE** ⚪: Variación < 3% (o <4% con dirección débil)

> ⚠️ **Nota**: La clasificación mensual (usada por `price_history_analyzer`) es engañosa porque el día 1 del mes rara vez representa la tendencia del mes completo. Todos los 84 datasets en `daily_daily_backtest_ready/` están clasificados por **precio real diario** contra klines de Binance Futures, no por mes.

### Ejemplo de uso:
```bash
# Analizar SOL
.venv/bin/python utils/data/price_history_analyzer.py --symbol SOL

# Recomendar 6 datasets
.venv/bin/python utils/data/price_history_analyzer.py --symbol SOL --recommend
```

---

## 📡 Paso 1: Descarga de Datos (Fetcher)

Tenemos dos opciones para descargar datos de alta fidelidad:

### Opción A: CryptoHFTData (Recomendado - Gratuito)

CryptoHFTData ofrece datos L2 y trades de alta fidelidad **100% gratis**.

#### Instalación:
```bash
.venv/bin/pip install cryptohftdata requests tqdm pyarrow zstandard pandas
```

#### Configuración:
La API key ya está configurada en `.env`:
```
CRYPTOHFTDATA_API_KEY=19fec542770cf27d4c7f006408def2cf9bd248a02e51e5f0c75602103bad7103
```

#### Flags:
| Flag | Descripción |
|------|-------------|
| `--symbol` | Par (ej: BTCUSDT) |
| `--start` | Fecha inicio (YYYY-MM-DD) |
| `--end` | Fecha fin (opcional, defecto = start) |
| `--types` | Tipos de datos: `incremental_book_L2 trades` (defecto ambos) |
| `--sequential` | **Para símbolos grandes (ETH, BTC)**: descarga 24h una por una en vez de en paralelo. Evita OOM en sistemas con ≤8GB RAM. Más lento (~15-20 min por día) pero funciona sin swap. |
| `--force` | Re-descargar aunque ya exista |

#### Ejemplos:
```bash
# Listar símbolos disponibles
.venv/bin/python utils/data/cryptohftdata_fetcher.py --symbol LTCUSDT --list

# Descargar 1 día (símbolos pequeños: APT, OP, LINK, etc.)
.venv/bin/python utils/data/cryptohftdata_fetcher.py --symbol LTCUSDT --start 2026-05-15

# Símbolos grandes (ETH, BTC) — usar --sequential para evitar OOM
.venv/bin/python utils/data/cryptohftdata_fetcher.py --symbol BTCUSDT --start 2026-01-31 --sequential

# Descargar 1 mes completo
.venv/bin/python utils/data/cryptohftdata_fetcher.py --symbol SOLUSDT --start 2026-05-01 --end 2026-05-31

# Solo trades (sin orderbook)
.venv/bin/python utils/data/cryptohftdata_fetcher.py --symbol BTCUSDT --start 2026-05-01 --types trades
```

#### Cobertura:
- Datos desde **enero 2026** en adelante
- 660+ símbolos en binance_futures, bybit, okx, hyperliquid, kraken
- **Sin restricción de "día 1 de cada mes"** → permite backtests mensuales continuos
- ⚠️ **OOM conocido**: ETH y BTC en modo paralelo requieren >8GB RAM. Usar `--sequential`.

---

### Opción B: Tardis.dev (Alternativa)

Utilizamos `utils/data/tardis_fetcher.py` para obtener datos de Tardis.dev.

#### Comando:
```bash
.venv/bin/python utils/data/tardis_fetcher.py --symbol <SYM> --start <YYYY-MM-DD>
```

#### Parámetros Clave:
*   `--symbol`: Par en formato Binance (ej: `LTCUSDT`).
*   `--start`: Fecha de inicio. (Nota: Sin API Key de Tardis, solo funciona el **día 1 de cada mes**).
*   `--end`: (Opcional) Fecha de fin.

#### Limitaciones:
*   ⚠️ Sin API key: Solo día 1 de cada mes
*   ⚠️ Con API key ($299/mes): Acceso completo

---

## ⚙️ Paso 2: Procesamiento e Inyección (Processor)

Utilizamos `utils/data/l2_processor.py` para convertir los archivos crudos en una base de datos SQLite con el Orderbook reconstruido.

### Comando:
```bash
.venv/bin/python utils/data/l2_processor.py --name <PATTERN> --symbol <SYM>
```

### ⚠️ Orden de Nomenclatura (Gotcha)
El fetcher crea raw files con orden `{date}_{symbol}`:
```
binance-futures_trades_2026-01-17_APTUSDT.csv.gz
```
Pero `l2_processor` usa `--name` como substring contra el filename. Para que funcione, los raw files deben tener el símbolo **antes** de la fecha:
```
binance-futures_trades_APTUSDT_2026-01-17.csv.gz
```
**Solución**: Renombrar antes de procesar:
```bash
mv raw/binance-futures_trades_2026-01-17_APTUSDT.csv.gz \
   raw/binance-futures_trades_APTUSDT_2026-01-17.csv.gz
# Luego procesar:
.venv/bin/python utils/data/l2_processor.py --name APTUSDT_2026-01-17 --symbol APTUSDT
```

### Reglas de Oro:
1.  **Pareja Obligatoria**: El script buscará automáticamente en `raw/` los archivos de `trades` y `incremental_book_L2` que coincidan con el `--name`. Si falta uno, el proceso falla por integridad.
2.  **Nombre del Output**: El archivo `.db` resultante tendrá el mismo nombre que el patrón `--name`. Renombrar el `.db` después para incluir el régimen (ej: `APTUSDT_TREND_UP_2026-01-17.db`).
3.  **Normalización**: El script guarda internamente el símbolo en formato limpio (`LTCUSDT`) para que el bot lo encuentre sin importar el formato de entrada.

---

## 🚀 Paso 3: Ejecución del Backtest

**Nota Importante:** Para auditorías de estrategia, **DEBES usar el orquestador** (`scripts/orchestrator.py`).
El orquestador automatiza el manejo de los datasets `daily_backtest_ready`, la concurrencia, la fusión de historiales y la ejecución del `ExitEdgeAuditor`.

### Auditoría Automática (Recomendado):
```bash
# Para auditorías de una moneda (ej. LTCUSDT)
python scripts/orchestrator.py --protocol single-coin-audit --symbol LTCUSDT

# Para auditorías generalizadas (todos los activos certificados)
python scripts/orchestrator.py --protocol generalized
```

### Ejecución Manual (Solo para pruebas aisladas):
Si necesitas correr una simulación aislada fuera de los protocolos de auditoría:

```bash
./.venv/bin/python backtest.py --depth-db-path data/datasets/daily_daily_backtest_ready/<NOMBRE>.db --symbol <SYM>
```

### Flags Importantes (Ejecución Manual):
*   `--depth-db-path`: Apunta al archivo `.db` en la carpeta `daily_backtest_ready`.
*   `--audit`: (Opcional) Para grabar señales y trazas de decisión en la base de datos temporal `historian.db`.

---

## 🧼 Mantenimiento y Reseteo

*   **Audit Reset**: El comando `utils/reset_data.py` (usado en workflows) **NO BORRA** la carpeta `data/datasets/`. Tus datasets procesados están seguros.
*   **Historian DB**: Los resultados de la ejecución se guardan en `data/historian.db`. Este archivo sí se borra en cada reset de auditoría.

---

## 🛠️ Esquema Interno (SQLite)

Si necesitas consultar los datos manualmente, las tablas son:
*   `market_trades`: Ticks de mercado (BUY/SELL).
*   `depth_snapshots`: Instantáneas del libro de órdenes (Top 5 niveles).
*   `price_candles`: Velas de 1m agregadas desde los trades.

---

---

## 📦 Inventario de Datasets (Jun 2026)

### Estándar: 2/2/2 por Símbolo
Cada símbolo tiene exactamente **2 TREND_UP + 2 TREND_DOWN + 2 BALANCE** = 6 datasets.

| Símbolo    | TREND_UP | TREND_DOWN | BALANCE | Estado |
|-----------|:--------:|:----------:|:-------:|:------:|
| ADAUSDT   | 2 | 2 | 2 | ✅ |
| APTUSDT   | 2 | 2 | 2 | ✅ |
| ARBUSDT   | 2 | 2 | 2 | ✅ |
| AVAXUSDT  | 2 | 2 | 2 | ✅ |
| BNBUSDT   | 2 | 2 | 2 | ✅ |
| BTCUSDT   | 2 | 2 | 2 | ✅ |
| DOGEUSDT  | 2 | 2 | 2 | ✅ |
| ETHUSDT   | 2 | 2 | 2 | ✅ |
| LINKUSDT  | 2 | 2 | 2 | ✅ |
| LTC       | 2 | 2 | 2 | ✅ |
| NEARUSDT  | 2 | 2 | 2 | ✅ |
| OPUSDT    | 2 | 2 | 2 | ✅ |
| SOLUSDT   | 2 | 2 | 2 | ✅ |
| XRPUSDT   | 2 | 2 | 2 | ✅ |
| **Total** | **28** | **28** | **28** | **84 ✅** |

### Datasets Mensuales
6 archivos en `data/datasets/monthly_daily_backtest_ready/`:
- 3 LTC (Mar–May 2026)
- 3 SOL (Mar–May 2026)

### Nomenclatura
- **Diarios**: `{SYMBOL}_{REGIME}_{YYYY-MM-DD}.db` (ej: `BTCUSDT_TREND_UP_2026-01-13.db`)
- **Mensuales**: `{SYM}_monthly_{YYYY_MM}.db` (ej: `LTC_monthly_2026_03.db`)

---

## ✅ Validación de Datos (CryptoHFTData vs Tardis)

### Resultados de Validación (BTCUSDT 2026-05-01)

#### TRADES: ✅ VÁLIDO
| Métrica | Valor |
|---------|-------|
| Diferencia filas | 1.88% (3,166,686 vs 3,107,012) |
| Columnas | ✅ Idénticas |
| ID overlap (primeros 10k) | 99.8% |
| Same-ID match (price/amount/side) | 100% |
| Time range | ✅ Idéntico |
| Price range | ✅ Idéntico (76265.40 - 78879.90) |
| Side distribution | ✅ Coincide (~50.4% sell / 49.6% buy) |

**Conclusión**: Los trades de CryptoHFTData contienen **los mismos datos que Tardis**.
La diferencia de 1.88% en filas sugiere filtrado marginal (ej: trades con precio=0).

#### ORDERBOOK: ✅ COMPATIBLE (UPDATE-ONLY)
El `l2_processor.py` **no usa `is_snapshot`** - solo aplica cada fila como un update
contra un `OrderBook` en memoria que empieza vacío. Aplica `book.update(side, price, amount)`
en cada fila sin distinguir entre snapshots y deltas.

CryptoHFTData incluye el depth completo en los primeros segundos de cada hora (~25K
niveles de precio únicos). Al concatenar las 24h en un solo CSV, el procesador recibe
el seed completo y mantiene el book correctamente durante todo el día.

**Sin cambios necesarios en l2_processor.py** - el fetcher nuevo convierte parquet→CSV
con el mismo formato que Tardis.

---

## 📋 Flujo de Trabajo Completo (Ejemplo)

### Descargar 1 día y convertirlo a .db (backtest ready):

```bash
# 1. Entorno
cd /home/chesterbelle/Casino-V3
source .env
export CRYPTOHFTDATA_API_KEY

# 2. Descargar 1 día (usar --sequential si es ETH/BTC)
.venv/bin/python utils/data/cryptohftdata_fetcher.py \
    --symbol LTCUSDT --start 2026-05-15

# 3. Renombrar raw files (l2_processor espera {symbol}_{date})
mv data/datasets/raw/binance-futures_trades_2026-05-15_LTCUSDT.csv.gz \
   data/datasets/raw/binance-futures_trades_LTCUSDT_2026-05-15.csv.gz
mv data/datasets/raw/binance-futures_incremental_book_L2_2026-05-15_LTCUSDT.csv.gz \
   data/datasets/raw/binance-futures_incremental_book_L2_LTCUSDT_2026-05-15.csv.gz

# 4. Procesar a SQLite
.venv/bin/python utils/data/l2_processor.py \
    --name LTCUSDT_2026-05-15 --symbol LTCUSDT

# 5. Renombrar con régimen (analizar el cambio % del día primero)
mv data/datasets/daily_daily_backtest_ready/LTCUSDT_2026-05-15.db \
   data/datasets/daily_daily_backtest_ready/LTCUSDT_BALANCE_2026-05-15.db

# 6. Ejecutar backtest
.venv/bin/python backtest.py \
    --depth-db-path data/datasets/daily_daily_backtest_ready/LTCUSDT_BALANCE_2026-05-15.db \
    --symbol LTCUSDT
```

### Construir datasets mensuales (LTC, SOL):

```bash
.venv/bin/python utils/data/build_monthly_datasets.py \
    --symbol LTCUSDT --months 3
```

### Si ya tienes datos de Tardis, validar CryptoHFTData:

```bash
# Descargar el mismo día de CryptoHFTData
.venv/bin/python utils/data/cryptohftdata_fetcher.py --symbol LTCUSDT --start 2024-01-01

# Validar contra Tardis
.venv/bin/python utils/data/validate_cryptohftdata.py \
    --tardis-file data/datasets/raw/binance-futures_incremental_book_L2_2024-01-01_LTCUSDT.csv.gz \
    --crypto-file data/datasets/raw/binance-futures_incremental_book_L2_2024-01-01_LTCUSDT.csv.gz
```
