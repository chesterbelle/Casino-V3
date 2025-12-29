#!/bin/bash
# Script de Validación Completa: Testing vs Backtesting
#
# Este script ejecuta el flujo completo de validación:
# 1. Testing en vivo (60 minutos)
# 2. Descarga de datos históricos
# 3. Backtesting (segundos)
# 4. Comparación de resultados

set -e  # Exit on error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuración
SYMBOL="BTC/USD:USD"
INTERVAL="1m"
MAX_CANDLES=60
PLAYER="paroli"

# Timestamps
START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Directorios
mkdir -p logs
mkdir -p data/validation
mkdir -p tests/validation_results

# Archivos de salida
TESTING_OUTPUT="logs/testing_${TIMESTAMP}.txt"
BACKTEST_OUTPUT="logs/backtest_${TIMESTAMP}.txt"
HISTORICAL_DATA="data/validation/historical_${TIMESTAMP}.csv"
COMPARISON_REPORT="tests/validation_results/comparison_${TIMESTAMP}.txt"

echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}🎰 VALIDACIÓN COMPLETA: Testing vs Backtesting${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "Configuración:"
echo -e "  Symbol:      ${SYMBOL}"
echo -e "  Interval:    ${INTERVAL}"
echo -e "  Max Candles: ${MAX_CANDLES}"
echo -e "  Player:      ${PLAYER}"
echo -e "  Start Time:  ${START_TIME}"
echo ""
echo -e "${YELLOW}⏱️  Duración estimada: 62 minutos (60 min testing + 2 min resto)${NC}"
echo ""

# Confirmación
read -p "¿Continuar? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}❌ Validación cancelada${NC}"
    exit 1
fi

# ============================================================================
# FASE 1: TESTING EN VIVO (60 minutos)
# ============================================================================
echo ""
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}📊 FASE 1: Testing en Vivo (60 minutos)${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "Ejecutando: python main.py --mode=testing --player=${PLAYER} --symbol=${SYMBOL} --interval=${INTERVAL} --max-candles=${MAX_CANDLES}"
echo -e "Salida guardándose en: ${TESTING_OUTPUT}"
echo ""

python main.py \
    --mode=testing \
    --player=${PLAYER} \
    --symbol=${SYMBOL} \
    --interval=${INTERVAL} \
    --max-candles=${MAX_CANDLES} \
    | tee ${TESTING_OUTPUT}

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error en testing en vivo${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Testing completado${NC}"

# Calcular tiempo de fin
END_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ============================================================================
# FASE 2: DESCARGA DE DATOS HISTÓRICOS (2 minutos)
# ============================================================================
echo ""
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}📥 FASE 2: Descarga de Datos Históricos${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "Descargando datos del período: ${START_TIME} - ${END_TIME}"
echo -e "Salida: ${HISTORICAL_DATA}"
echo ""

python tests/validation/download_historical_data_csv.py \
    --symbol=${SYMBOL} \
    --timeframe=${INTERVAL} \
    --start="${START_TIME}" \
    --end="${END_TIME}" \
    --output=${HISTORICAL_DATA}

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error descargando datos históricos${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Datos descargados${NC}"

# ============================================================================
# FASE 3: BACKTESTING (segundos)
# ============================================================================
echo ""
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}🔄 FASE 3: Backtesting${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "Ejecutando: python main.py --mode=backtest --player=${PLAYER} --data=${HISTORICAL_DATA} --max-candles=${MAX_CANDLES}"
echo -e "Salida guardándose en: ${BACKTEST_OUTPUT}"
echo ""

python main.py \
    --mode=backtest \
    --player=${PLAYER} \
    --data=${HISTORICAL_DATA} \
    --max-candles=${MAX_CANDLES} \
    | tee ${BACKTEST_OUTPUT}

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error en backtesting${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Backtesting completado${NC}"

# ============================================================================
# FASE 4: COMPARACIÓN DE RESULTADOS
# ============================================================================
echo ""
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}📊 FASE 4: Comparación de Resultados${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""

python tests/validation/compare_main_results.py \
    --testing=${TESTING_OUTPUT} \
    --backtest=${BACKTEST_OUTPUT} \
    | tee ${COMPARISON_REPORT}

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error en comparación${NC}"
    exit 1
fi

# ============================================================================
# RESUMEN FINAL
# ============================================================================
echo ""
echo -e "${BLUE}================================================================================${NC}"
echo -e "${BLUE}🏁 VALIDACIÓN COMPLETADA${NC}"
echo -e "${BLUE}================================================================================${NC}"
echo ""
echo -e "Archivos generados:"
echo -e "  Testing output:     ${TESTING_OUTPUT}"
echo -e "  Historical data:    ${HISTORICAL_DATA}"
echo -e "  Backtest output:    ${BACKTEST_OUTPUT}"
echo -e "  Comparison report:  ${COMPARISON_REPORT}"
echo ""
echo -e "${GREEN}✅ Validación completa finalizada${NC}"
echo ""
