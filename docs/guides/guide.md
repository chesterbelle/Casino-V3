# 🎰 Casino-V3 CLI Guide

Quick reference for running the bot via command line interface.

## 🚀 Quick Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--exchange` | `binance` | Exchange driver (`binance`, `hyperliquid`) |
| `--symbol` | `BTC/USDT:USDT` | Trading Pair (or `MULTI` for multi-pair) |
| `--mode` | `testing` | Execution Mode (`live`, `testing`, `demo`) |
| `--bet-size` | `0.01` | Position size percent (e.g. `0.01` = 1%) |
| `--timeout` | `None` | **[New]** Auto-stop after N minutes (e.g., `150`) |
| `--close-on-exit`| `False` | **[New]** Force close ALL positions on stop |
| `--wallet` | `None` | Wallet address (Override ENV) |
| `--key` | `None` | Private Key (Override ENV) |

---

## 🛠️ Usage Examples

### 1. Controlled Test Session (Recommended)
Run for a fixed time in demo mode, and clean up everything when done.
Perfect for validating logic or monitoring stability.

```bash
# Run for 2.5 hours (150m) and close everything at the end
python main.py --mode demo --symbol MULTI --timeout 150 --close-on-exit
```

### 2. Continuous Production
Run indefinitely. If manual stop is needed (Ctrl+C), it will **preserve** positions safely.

```bash
# Live mode, 2% risk per trade
python main.py --mode live --symbol MULTI --bet-size 0.02
```

### 3. Quick Debugging
Run locally with a specific symbol to test signal generation.

```bash
# Debug BTC specifically
python main.py --mode testing --symbol BTC/USDT:USDT
```

---

## ℹ️ detailed Flags

### `--close-on-exit`
- **False (Default):** "Safe Mode". On shutdown (Ctrl+C or Timeout), it cancels pending orders but **leaves open positions active**. Prevents accidental loss realization during restart.
- **True:** "Cleanup Mode". Sends Market Close orders for ALL open positions and waits for them to close before shutting down. Useful for unnatended test sessions.

### `--mode`
- **live:** Real money, real API calls.
- **demo:** Real market data, paper trading (simulated execution).
- **testing:** Simulated data feed (if configured) or dry-run.

### `--symbol`
- **Specific Pair:** `BTC/USDT:USDT` (Binance Futures format).
- **MULTI:** Automatically fetches top liquid pairs from config and trades them all.
