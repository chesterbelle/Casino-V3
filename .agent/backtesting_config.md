# 📊 Configuración de Backtesting de Alta Fidelidad (Phase 1300)

Este documento detalla la infraestructura centralizada de datos L2 y Trades para Casino-V3, diseñada para eliminar la dependencia de CSVs y garantizar paridad determinista.

---

## 🏗️ Arquitectura de Datos

El sistema separa los datos en dos capas para evitar borrados accidentales durante auditorías:

1.  **Raw Data (`data/datasets/raw/`)**: Archivos originales `.csv.gz` descargados de Tardis o Binance.
2.  **Backtest Ready (`data/datasets/backtest_ready/`)**: Archivos `.db` (SQLite) procesados, listos para la simulación.

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

### Clasificación por condición:
*   **TREND_UP** 🟢: Subida sostenida >10%, dirección consistente (>55% días directionales)
*   **TREND_DOWN** 🔴: Bajada sostenida >10%, dirección consistente
*   **BALANCE** ⚪: Rango lateral <5% variación

### Ejemplo de uso:
```bash
# Analizar SOL
.venv/bin/python utils/data/price_history_analyzer.py --symbol SOL

# Recomendar 6 datasets para ILLIQUID_SPEC
.venv/bin/python utils/data/price_history_analyzer.py --symbol SOL --recommend
```

---

## 📡 Paso 1: Descarga de Datos (Fetcher)

Utilizamos `utils/data/tardis_fetcher.py` para obtener datos de alta fidelidad.

### Comando:
```bash
.venv/bin/python utils/data/tardis_fetcher.py --symbol <SYM> --start <YYYY-MM-DD>
```

### Parámetros Clave:
*   `--symbol`: Par en formato Binance (ej: `LTCUSDT`).
*   `--start`: Fecha de inicio. (Nota: Sin API Key de Tardis, solo funciona el **día 1 de cada mes**).
*   `--end`: (Opcional) Fecha de fin.

---

## ⚙️ Paso 2: Procesamiento e Inyección (Processor)

Utilizamos `utils/data/l2_processor.py` para convertir los archivos crudos en una base de datos SQLite con el Orderbook reconstruido.

### Comando:
```bash
.venv/bin/python utils/data/l2_processor.py --name <PATTERN> --symbol <SYM>
```

### Reglas de Oro:
1.  **Pareja Obligatoria**: El script buscará automáticamente en `raw/` los archivos de `trades` y `incremental_book_L2` que coincidan con el `--name`. Si falta uno, el proceso falla por integridad.
2.  **Nombre del Output**: El archivo `.db` resultante tendrá el mismo nombre que el patrón `--name` que proporciones. Esto te permite renombrar tus archivos en `raw/` a algo descriptivo (ej: `bullmarket_test`) antes de procesarlos.
3.  **Normalización**: El script guarda internamente el símbolo en formato limpio (`LTCUSDT`) para que el bot lo encuentre sin importar el formato de entrada.

---

## 🚀 Paso 3: Ejecución del Backtest

**Nota Importante:** Para auditorías de estrategia, **DEBES usar el orquestador** (`scripts/orchestrator.py`).
El orquestador automatiza el manejo de los datasets `backtest_ready`, la concurrencia, la fusión de historiales y la ejecución del `ExitEdgeAuditor`.

### Auditoría Automática (Recomendado):
```bash
# Para auditorías de una moneda (ej. LTCUSDT)
python scripts/orchestrator.py --protocol single-coin --symbol LTCUSDT

# Para auditorías generalizadas (todos los activos certificados)
python scripts/orchestrator.py --protocol generalized
```

### Ejecución Manual (Solo para pruebas aisladas):
Si necesitas correr una simulación aislada fuera de los protocolos de auditoría:

```bash
./.venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/<NOMBRE>.db --symbol <SYM>
```

### Flags Importantes (Ejecución Manual):
*   `--depth-db-path`: Apunta al archivo `.db` en la carpeta `backtest_ready`.
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
