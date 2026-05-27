#!/bin/bash
cd /home/chesterbelle/Casino-V3
rm -f data/historian_*.db
setsid .venv/bin/python scripts/orchestrator.py --protocol generalized > logs/orchestrator_run.log 2>&1
