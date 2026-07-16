#!/bin/bash
cd /home/chesterbelle/Casino-V3
echo "Starting at $(date)" > data/db_vault/avax_tactical_optimization.log
setsid .venv/bin/python -u scripts/cluster_optimizer.py \
  --cluster AVAX_NOISY_UNCERTAIN \
  --only tactical_absorption \
  --iterations 50 \
  --study-db data/db_vault/avax_tactical.db \
  --resume \
  --output data/db_vault/avax_tactical_results.json \
  >> data/db_vault/avax_tactical_optimization.log 2>&1 </dev/null &
PID=$!
echo $PID
echo $PID > /tmp/avax_opt.pid
echo "Launched PID $PID"
