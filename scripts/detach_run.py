#!/usr/bin/env python3
"""Launch generalized protocol as a truly detached process."""
import os
import subprocess
import sys

cmd = [
    sys.executable,
    "scripts/orchestrator.py",
    "--protocol",
    "generalized",
]
log = open("logs/orchestrator_run.log", "w")

# Create new process group, detach from parent
proc = subprocess.Popen(
    cmd,
    stdout=log,
    stderr=subprocess.STDOUT,
    preexec_fn=os.setpgrp,  # new process group, immune to SIGHUP
)
print(f"PID: {proc.pid}")
