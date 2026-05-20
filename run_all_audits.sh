#!/bin/bash
echo "🚀 Iniciando Generalized Edge Audit para 10 monedas..." > audit.log

COINS=("ADAUSDT" "AVAXUSDT" "BNBUSDT" "DOGEUSDT" "ETHUSDT" "LINKUSDT" "LTCUSDT" "SOLUSDT" "SUIUSDT" "XRPUSDT")

for COIN in "${COINS[@]}"; do
  echo "⏳ Ejecutando backtest para $COIN..." | tee -a audit.log
  .venv/bin/python backtest.py --depth-db-path data/datasets/backtest_ready/2024-01-01_${COIN}.db --symbol $COIN --audit >> audit.log 2>&1
  echo "✅ Backtest completado para $COIN" | tee -a audit.log
done

echo "🏁 ALL 10 BACKTESTS COMPLETE" | tee -a audit.log
