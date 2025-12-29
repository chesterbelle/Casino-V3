#!/bin/bash
# Script para ejecutar validación completa de Testing vs Backtesting
# Uso: ./run_validation_test.sh [num_candles]

set -e

NUM_CANDLES=${1:-10}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="tests/validation_results"

mkdir -p "$RESULTS_DIR"

echo "================================================================================"
echo "🧪 VALIDACIÓN: Testing vs Backtesting"
echo "================================================================================"
echo "Velas: $NUM_CANDLES"
echo "Timestamp: $TIMESTAMP"
echo "================================================================================"

# Paso 1: Ejecutar Testing
echo ""
echo "📝 PASO 1: Ejecutando Testing Mode..."
echo "Duración estimada: $NUM_CANDLES minutos"
echo "================================================================================"

python main.py \
    --mode=testing \
    --player=paroli \
    --symbol=BTC/USD:USD \
    --interval=1m \
    --max-candles=$NUM_CANDLES \
    2>&1 | tee "$RESULTS_DIR/testing_${TIMESTAMP}.log"

# Extraer balance inicial del log
INITIAL_BALANCE=$(grep "Initial Balance:" "$RESULTS_DIR/testing_${TIMESTAMP}.log" | tail -1 | awk '{print $3}' | tr -d '$,')

echo ""
echo "================================================================================"
echo "✅ Testing completado"
echo "💰 Balance inicial detectado: \$$INITIAL_BALANCE"
echo "================================================================================"

# Paso 2: Preparar datos para backtest
# TODO: Implementar descarga de datos históricos

# Paso 3: Ejecutar Backtest con el mismo balance
echo ""
echo "📝 PASO 3: Ejecutando Backtest Mode..."
echo "💰 Usando balance inicial: \$$INITIAL_BALANCE"
echo "================================================================================"

# TODO: Ejecutar backtest cuando tengamos los datos históricos
# python main.py \
#     --mode=backtest \
#     --player=paroli \
#     --data="$RESULTS_DIR/historical_data_${TIMESTAMP}.csv" \
#     --max-candles=$NUM_CANDLES \
#     --initial-balance=$INITIAL_BALANCE \
#     2>&1 | tee "$RESULTS_DIR/backtest_${TIMESTAMP}.log"

echo ""
echo "================================================================================"
echo "✅ VALIDACIÓN COMPLETADA"
echo "================================================================================"
echo "Logs guardados en:"
echo "  - Testing:  $RESULTS_DIR/testing_${TIMESTAMP}.log"
echo "  - Backtest: $RESULTS_DIR/backtest_${TIMESTAMP}.log (TODO)"
echo ""
echo "Balance inicial usado: \$$INITIAL_BALANCE"
echo "================================================================================"
