#!/bin/bash
# Ronda 1: Validación con 10 velas
# Duración: ~15 minutos

set -e  # Exit on error

echo "================================================================================"
echo "🎯 RONDA 1: Validación con 10 velas"
echo "================================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Testing
echo -e "${YELLOW}📊 PASO 1: Ejecutando testing (10 velas, ~10 minutos)...${NC}"
echo ""

python main.py testing \
    --player paroli \
    --symbol BTC/USDT:USDT \
    --interval 1m \
    --max-candles 10

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Testing falló${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Testing completado${NC}"
echo ""

# Get the latest testing log
TESTING_LOG=$(ls -t logs/testing_*.json 2>/dev/null | head -1)

if [ -z "$TESTING_LOG" ]; then
    echo -e "${RED}❌ No se encontró log de testing${NC}"
    exit 1
fi

echo "📝 Log de testing: $TESTING_LOG"
echo ""

# Extract initial balance from testing log
INITIAL_BALANCE=$(python3 -c "import json; print(json.load(open('$TESTING_LOG'))['initial_balance'])")
echo -e "${YELLOW}💰 Balance inicial del testing: \$$INITIAL_BALANCE${NC}"
echo ""

# Extract timestamps from testing log
START_TIME=$(python3 -c "
import json
from datetime import datetime
data = json.load(open('$TESTING_LOG'))
# Parse ISO timestamp and format for download script
dt = datetime.fromisoformat(data['timestamp'])
print(dt.strftime('%Y-%m-%d %H:%M:%S'))
")

# Calculate end time (start + 10 minutes)
END_TIME=$(python3 -c "
from datetime import datetime, timedelta
start = datetime.strptime('$START_TIME', '%Y-%m-%d %H:%M:%S')
end = start + timedelta(minutes=10)
print(end.strftime('%Y-%m-%d %H:%M:%S'))
")

echo "📅 Período: $START_TIME → $END_TIME"
echo ""

# Step 2: Download historical data
echo -e "${YELLOW}📥 PASO 2: Descargando datos históricos...${NC}"
echo ""

python tests/validation/download_historical_data.py \
    --start "$START_TIME" \
    --end "$END_TIME" \
    --symbol BTC/USDT \
    --interval 1m \
    --exchange bybit \
    --output data/validation/historical_ronda1.csv

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Descarga de datos falló${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Datos descargados${NC}"
echo ""

# Step 3: Backtest
echo -e "${YELLOW}🎮 PASO 3: Ejecutando backtest...${NC}"
echo ""

python main.py backtest \
    --data data/validation/historical_ronda1.csv \
    --player paroli \
    --initial-balance $INITIAL_BALANCE \
    --max-candles 10

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Backtest falló${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Backtest completado${NC}"
echo ""

# Get the latest backtest log
BACKTEST_LOG=$(ls -t logs/backtest_*.json 2>/dev/null | head -1)

if [ -z "$BACKTEST_LOG" ]; then
    echo -e "${RED}❌ No se encontró log de backtest${NC}"
    exit 1
fi

echo "📝 Log de backtest: $BACKTEST_LOG"
echo ""

# Step 4: Compare results
echo -e "${YELLOW}📊 PASO 4: Comparando resultados...${NC}"
echo ""

python tests/validation/compare_results.py \
    --testing "$TESTING_LOG" \
    --backtest "$BACKTEST_LOG" \
    --tolerance 0.5 \
    --output logs/comparison_ronda1.txt

COMPARISON_RESULT=$?

echo ""

if [ $COMPARISON_RESULT -eq 0 ]; then
    echo -e "${GREEN}================================================================================${NC}"
    echo -e "${GREEN}🎉 RONDA 1 COMPLETADA: ✅ VALIDACIÓN EXITOSA${NC}"
    echo -e "${GREEN}================================================================================${NC}"
    echo ""
    echo "📝 Archivos generados:"
    echo "   - Testing: $TESTING_LOG"
    echo "   - Backtest: $BACKTEST_LOG"
    echo "   - Comparación: logs/comparison_ronda1.txt"
    echo "   - Datos: data/validation/historical_ronda1.csv"
    echo ""
    echo "🚀 Próximo paso: Ejecutar Ronda 2 (30 velas)"
    exit 0
else
    echo -e "${RED}================================================================================${NC}"
    echo -e "${RED}❌ RONDA 1 COMPLETADA: VALIDACIÓN FALLIDA${NC}"
    echo -e "${RED}================================================================================${NC}"
    echo ""
    echo "📝 Revisar:"
    echo "   - Testing: $TESTING_LOG"
    echo "   - Backtest: $BACKTEST_LOG"
    echo "   - Comparación: logs/comparison_ronda1.txt"
    echo ""
    echo "⚠️  Analizar diferencias antes de continuar"
    exit 1
fi
