#!/bin/sh
set -euo pipefail

# Ronda 2 - Binance (30 velas)
# - Ejecuta demo trading por ~30 velas (modo demo/testnet configurado)
# - Descarga datos históricos de Binance para el rango
# - Ejecuta backtest con los datos descargados
# - Compara resultados

ROOT_DIR=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT_DIR"

echo "[ronda2] Iniciando Ronda 2 (Binance)"

# Paths
DEMO_LOGS_DIR="logs"
HIST_DATA="data/validation/historical_ronda2.csv"
BACKTEST_LOGS_DIR="logs"
COMPARISON_LOG="logs/comparison_ronda2.txt"

# 1) Ejecutar demo trading con los flags indicados por el usuario
echo "[ronda2] Ejecutando demo trading (30 velas)"
./.venv/bin/python main.py --mode=demo --exchange=binance --player=paroli --symbol=LTC/USDT:USDT --interval=1m --max-candles=30 || true

# Intenta detectar el último demo log generado
DEMO_LOG=$(ls -t ${DEMO_LOGS_DIR}/demo_*.json 2>/dev/null | head -n1 || true)
if [ -z "$DEMO_LOG" ]; then
  echo "[ronda2] No se encontró demo log en ${DEMO_LOGS_DIR}. Continúo, pero revisa la ejecución demo."
else
  echo "[ronda2] Demo log: $DEMO_LOG"
fi

# 2) Extraer timestamps del demo log y calcular fechas para descarga
if [ -n "$DEMO_LOG" ] && [ -f "$DEMO_LOG" ]; then
  echo "[ronda2] Extrayendo timestamps del demo log"
  # Extraer primer y último timestamp del log
  TIMESTAMPS=$(python3 - "$DEMO_LOG" <<'PY'
import json, sys
from datetime import datetime, timedelta

log_path = sys.argv[1]
with open(log_path) as f:
    data = json.load(f)

# Buscar timestamps en candle_timestamps (nuevo campo agregado)
ts_list = data.get('candle_timestamps', [])

if ts_list:
    # Primer y último timestamp en milisegundos
    first_ts = min(ts_list)
    last_ts = max(ts_list)

    # Convertir a datetime SIN margen adicional
    start_dt = datetime.fromtimestamp(first_ts / 1000)
    end_dt = datetime.fromtimestamp(last_ts / 1000)

    # Formato para el script de descarga
    print(f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
PY
)

  if [ -n "$TIMESTAMPS" ]; then
    START_DATE=$(echo $TIMESTAMPS | cut -d' ' -f1-2)
    END_DATE=$(echo $TIMESTAMPS | cut -d' ' -f3-4)
    echo "[ronda2] Período detectado: $START_DATE → $END_DATE"
  else
    echo "[ronda2] No se encontraron timestamps en el log, usando período por defecto"
    # Usar últimas 2 horas como fallback
    START_DATE=$(date -d '2 hours ago' '+%Y-%m-%d %H:%M:%S')
    END_DATE=$(date '+%Y-%m-%d %H:%M:%S')
  fi
else
  echo "[ronda2] No se encontró demo log, usando período por defecto"
  START_DATE=$(date -d '2 hours ago' '+%Y-%m-%d %H:%M:%S')
  END_DATE=$(date '+%Y-%m-%d %H:%M:%S')
fi

# 3) Descargar datos históricos de Binance para la ventana
echo "[ronda2] Descargando datos históricos de Binance → ${HIST_DATA}"
python tests/validation/download_historical_data.py --exchange binance --symbol LTC/USDT:USDT --interval 1m --start "$START_DATE" --end "$END_DATE" --output ${HIST_DATA} || echo "[ronda2] download script devolvió error; revisar tests/validation/download_historical_data.py"

# 3.1) Filtrar CSV para que contenga SOLO las velas que el demo procesó
if [ -n "$DEMO_LOG" ] && [ -f "$DEMO_LOG" ] && [ -f "${HIST_DATA}" ]; then
  echo "[ronda2] Filtrando CSV para coincidir con velas procesadas en demo"
  python3 - "$DEMO_LOG" "${HIST_DATA}" <<'PY'
import json, sys, pandas as pd

demo_log = sys.argv[1]
csv_file = sys.argv[2]

# Leer timestamps del demo
with open(demo_log) as f:
    demo_data = json.load(f)
demo_timestamps = set(demo_data.get('candle_timestamps', []))

if not demo_timestamps:
    print(f"⚠️ No candle_timestamps in demo log, skipping filter")
    sys.exit(0)

# Leer CSV
df = pd.read_csv(csv_file)

# Filtrar solo las velas que el demo procesó
df_filtered = df[df['timestamp'].isin(demo_timestamps)]

print(f"📊 Filtered CSV: {len(df)} -> {len(df_filtered)} candles")

# Sobrescribir CSV con datos filtrados
df_filtered.to_csv(csv_file, index=False)
PY
fi

# 3.5) Extraer balance inicial del demo log para usar en backtest
if [ -n "$DEMO_LOG" ] && [ -f "$DEMO_LOG" ]; then
  INITIAL_BALANCE=$(python3 - "$DEMO_LOG" <<'PY'
import json, sys
log_path = sys.argv[1]
with open(log_path) as f:
    data = json.load(f)
print(data.get('initial_balance', 10000))
PY
)
  echo "[ronda2] Balance inicial detectado: $INITIAL_BALANCE"
else
  INITIAL_BALANCE=10000
  echo "[ronda2] Usando balance por defecto: $INITIAL_BALANCE"
fi

# 4) Ejecutar backtest con los datos descargados y el mismo balance inicial
echo "[ronda2] Ejecutando backtest con ${HIST_DATA} (balance inicial: $INITIAL_BALANCE)"
./.venv/bin/python main.py --mode=backtest --player=paroli --data=${HIST_DATA} --initial-balance=$INITIAL_BALANCE || true

# 5) Comparar resultados (intenta usar compare_results.py)
echo "[ronda2] Comparando resultados"
BACKTEST_LOG=$(ls -t ${BACKTEST_LOGS_DIR}/backtest_*.json 2>/dev/null | head -n1 || true)

if [ -n "$DEMO_LOG" ] && [ -n "$BACKTEST_LOG" ]; then
  echo "[ronda2] Demo log: $DEMO_LOG"
  echo "[ronda2] Backtest log: $BACKTEST_LOG"
  python tests/validation/compare_results.py --testing "$DEMO_LOG" --backtest "$BACKTEST_LOG" --output ${COMPARISON_LOG} || echo "[ronda2] compare script devolvió error"
else
  echo "[ronda2] No se encontraron logs para comparar (Demo: ${DEMO_LOG:-None}, Backtest: ${BACKTEST_LOG:-None})"
fi

echo "[ronda2] Finalizado. Revisa ${COMPARISON_LOG} y los logs en logs/."

exit 0
