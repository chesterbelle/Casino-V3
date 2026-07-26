#!/bin/bash
# scripts/run_non_regression.sh
# Corre el Edge Audit secuencialmente para las 9 monedas validadas

SYMBOLS=("ARBUSDT" "NEARUSDT" "OPUSDT" "APTUSDT" "LINKUSDT" "DOGEUSDT" "ADAUSDT" "BNBUSDT" "XRPUSDT")
LOG_DIR="/tmp/casino_non_regression"

mkdir -p "$LOG_DIR"

echo "==============================================="
echo "INICIANDO NON-REGRESSION TEST MASIVO (FASE 1)"
echo "==============================================="

for SYMBOL in "${SYMBOLS[@]}"; do
    echo "[$(date '+%H:%M:%S')] Iniciando Audit para $SYMBOL..."
    LOG_FILE="$LOG_DIR/audit_${SYMBOL}.log"

    # Run the backtest runner
    python3 scripts/backtest_runner.py --mode audit --symbol "$SYMBOL" > "$LOG_FILE" 2>&1

    if [ $? -eq 0 ]; then
        echo "[$(date '+%H:%M:%S')] ✅ Completado: $SYMBOL. Log: $LOG_FILE"
        # Try to extract Net Taker from the log if available
        NET_TAKER=$(grep -i "Net Taker" "$LOG_FILE" | tail -n 1)
        if [ ! -z "$NET_TAKER" ]; then
            echo "   -> $NET_TAKER"
        fi
    else
        echo "[$(date '+%H:%M:%S')] ❌ ERROR en: $SYMBOL. Revisa el log: $LOG_FILE"
        echo "Abortando el test para investigar la regresión."
        exit 1
    fi
    echo "-----------------------------------------------"
done

echo "==============================================="
echo "TEST FINALIZADO COMPLETAMENTE."
echo "==============================================="
