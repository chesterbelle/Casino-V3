"""
Validators - Integration Tests for Trading System
==================================================

This package contains end-to-end integration tests that validate
the complete trading flow on live exchanges (testnet/live).

Available Validators:
--------------------

1. trading_flow_validator.py
   - Validates complete trading flow with TP/SL
   - Tests OCO manual functionality
   - Monitors natural TP/SL execution

   Usage:
   python -m utils.validators.trading_flow_validator \
       --exchange=binance --symbol=LTCUSDT --mode=demo \
       --execute-orders --wait=3600 --tp=0.003 --sl=0.003

2. test_concurrent_positions.py
   - Validates multiple concurrent positions
   - Tests independent TP/SL management per position
   - Verifies OCO doesn't interfere between positions

   Usage:
   python -m utils.validators.test_concurrent_positions \
       --exchange=binance --symbol=LTCUSDT --mode=demo

Purpose:
--------
These validators test the REAL system behavior on actual exchanges,
not mocked/simulated environments. They verify:

- Order creation and execution
- TP/SL automatic triggering
- Position management
- OCO manual cleanup
- Multi-position handling
- Error recovery

Run these before deploying to production to ensure system stability.
"""
