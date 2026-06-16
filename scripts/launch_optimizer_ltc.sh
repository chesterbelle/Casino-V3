#!/usr/bin/env bash
cd /home/chesterbelle/Casino-V3
LOG="results/optimization_ltc.log"
STUDY="results/optuna_ltc_fb_le.db"
nohup .venv/bin/python -u scripts/cluster_optimizer.py \
  --cluster LTC_NOISY_UNCERTAIN_1 \
  --coin LTC \
  --iterations 50 \
  --study-db "$STUDY" \
  > "$LOG" 2>&1 &
echo "PID: $!"
