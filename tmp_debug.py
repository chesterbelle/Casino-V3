import signal
import subprocess
import time

print("Running backtest for 40s")
p = subprocess.Popen(
    [
        ".venv/bin/python",
        "-X",
        "faulthandler",
        "backtest.py",
        "--data",
        "data/raw/LTCUSDT_trades_2026_01.csv",
        "--symbol",
        "LTCUSDT",
        "--balance",
        "10000",
    ]
)
time.sleep(40)
print("Sending SIGABRT to force faulthandler dump...")
p.send_signal(signal.SIGABRT)
p.wait()
