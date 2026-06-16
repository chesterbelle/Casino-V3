#!/usr/bin/env python3
"""Launcher for cluster_optimizer that survives bash timeouts."""
import os
import subprocess

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_BASE)

cmd = [
    os.path.join(_BASE, ".venv", "bin", "python"),
    "-u",
    "scripts/cluster_optimizer.py",
    "--cluster",
    "THIN_VOLATILE",
    "--coin",
    "XRPUSDT",
    "--iterations",
    "3",
    "--single-dataset",
    "--filter",
    "2024-11",
]

log_path = os.path.join(_BASE, "results", "optimization_run.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

with open(log_path, "w") as log:
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=_BASE,
        start_new_session=True,
    )

status_path = os.path.join(_BASE, "results", "optimization_status.txt")
with open(status_path, "w") as f:
    f.write(f"RUNNING pid={proc.pid}\n")

print(f"Optimizer launched (PID={proc.pid}). Log: {log_path}")
