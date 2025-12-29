"""
Configuration file for pytest.
This file ensures the project root is in the Python path.
"""

import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Prevent pytest from collecting legacy/integration scripts moved or removed from active suite.
# This keeps files present on disk but excluded from automated test runs.
collect_ignore = [
    "test_backtest_croupier_v2.py",
    "test_bybit_complete.py",
    "test_bybit_connector.py",
    "test_croupier_v2_integration.py",
    "test_kraken_tpsl_manual.py",
    "validate_kraken_oco.py",
    "test_oco_execution_debug.py",
    "test_oco_execution_debug_backtest.py",
    "test_oco_monitor.py",
    "test_oco_monitor_backtest.py",
    "test_oco_monitor_simple.py",
    "test_connector_oco.py",
]
