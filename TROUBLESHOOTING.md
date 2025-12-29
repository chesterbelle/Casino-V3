# Troubleshooting Guide 🔧

Common issues and solutions for Casino-V3.

---

## Installation Issues

### ModuleNotFoundError: No module named 'X'

**Cause**: Missing Python dependencies

**Solution**:
```bash
pip install -r requirements.txt

# If using venv
source .venv/bin/activate
pip install -r requirements.txt
```

### ImportError: aiolimiter

**Cause**: Package not install or wrong Python environment

**Solution**:
```bash
# Verify Python version
python --version  # Should be 3.13+

# Reinstall dependencies
pip install --upgrade aiolimiter aiohttp
```

---

## API & Authentication

### "Invalid API key format" (-2015)

**Cause**: Malformed or missing API key

**Solutions**:
1. Check `.env` file exists in project root
2. Verify no extra spaces in API key/secret
3. Regenerate API keys on Binance
4. Ensure using correct mode (demo vs live)

```bash
# Verify .env format
cat .env | grep BINANCE
# Should show:
# BINANCE_API_KEY=your_key
# BINANCE_API_SECRET=your_secret
```

### "Signature invalid" (-1022)

**Cause**: Time sync issue or incorrect signature

**Solutions**:
```bash
# 1. Sync system time
sudo ntpdate -s time.nist.gov

# 2. Check Binance server time offset
python -c "from exchanges.connectors.binance import *; print('Time offset OK')"

# 3. Regenerate API keys
```

### HTTP session not initialized

**Cause**: Connector disconnected prematurely

**Solution**: This usually occurs during shutdown. If happening during trading:
```bash
# 1. Check network connectivity
ping api.binance.com

# 2. Restart bot
# 3. If persists, file an issue with logs
```

---

## Trading Issues

### "Pending Order In-Flight" (Frequent)

**Cause**: Lock protection preventing duplicate orders

**Diagnosis**:
```bash
# Check if locks are being released
grep "Pending Order" redo_round_1_v4.log | wc -l

# If count > 100 in short time, may indicate issue
```

**Solutions**:
1. This is **normal** behavior during signal storms
2. Locks auto-release after order completes
3. If symbol permanently stuck, check `state_audit.py`

### Positions Not Closing on Shutdown

**Cause**: Shutdown sequence error or connector disconnect

**Diagnosis**:
```bash
# Check shutdown logs
grep "Emergency sweep" bot.log

# Audit exchange state
python state_audit.py --symbol MULTI
```

**Solution**:
```bash
# Manual cleanup
python sweep_exchange.py --symbol MULTI
```

### "Notional too small" (-4164)

**Cause**: Position size below minimum notional value (~5 USDT on Binance)

**Solutions**:
```bash
# Increase bet size
python main.py --bet-size 0.1  # Was 0.05

# Or reduce leverage (increases margin)
python main.py --leverage 5  # Was 10
```

---

## WebSocket Issues

### Frequent WebSocket Reconnections

**Cause**: Network instability or firewall

**Diagnosis**:
```bash
# Check connection stability
ping -c 100 stream.binancefuture.com

# Monitor reconnections
grep "Reconnecting" bot.log | wc -l
```

**Solutions**:
1. Check firewall rules allow WebSocket (port 443)
2. Verify stable internet connection
3. If on VPN, try without VPN
4. Increase ping interval in config

### "Max streams exceeded"

**Cause**: Too many concurrent WebSocket streams

**Solution**:
- Binance limit: 200 streams
- Each symbol uses ~2 streams (ticker + trades)
- Max symbols: ~90 (we use 50 by default)

```bash
# Reduce symbols in MULTI mode
# Edit config/symbols.json - reduce list
```

---

## Performance Issues

### High CPU Usage

**Cause**: Sensor workers computing indicators

**Diagnosis**:
```bash
top -p $(pgrep -f main.py)
```

**Solutions**:
```bash
# Reduce sensor workers
# Edit .env
SENSOR_WORKERS=2  # Was 4

# Or reduce active symbols
python main.py --symbol BTC/USDT  # Single symbol mode
```

### High Memory Usage

**Cause**: Long runtime accumulating WebSocket state

**Diagnosis**:
```bash
ps aux | grep main.py | awk '{print $6/1024 " MB"}'
```

**Solutions**:
1. Restart bot periodically (use `--timeout`)
2. Clear old logs/state files
3. Normal: 200-500MB, High: >1GB

```bash
# Clean old state files
rm -rf state/*.backup_*.json
rm -rf persistence/*.json
```

---

## Metrics & Monitoring

### Port 8000 Already in Use

**Cause**: Previous bot instance still running

**Solutions**:
```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 $(lsof -t -i:8000)

# Or change metrics port
# Edit .env
METRICS_PORT=8001
```

### Metrics Not Updating

**Cause**: Metrics server disabled or crashed

**Diagnosis**:
```bash
# Check if metrics endpoint responds
curl http://localhost:8000/metrics
```

**Solutions**:
1. Verify `ENABLE_METRICS=true` in `.env`
2. Check logs for metrics server errors
3. Restart bot

---

## State & Data Issues

### "Potential Orphans/Zombies" in state_audit.py

**Cause**: Desync between bot state and exchange

**Diagnosis**:
```bash
python state_audit.py --symbol MULTI
```

**Output Example**:
```
INFO:Audit:Summary: Symbols Checked=5, Potential Orphans/Zombies=2
```

**Solutions**:
```bash
# Clean orphan orders/positions
python sweep_exchange.py --symbol MULTI

# Verify cleanup
python state_audit.py --symbol MULTI
# Should show: Potential Orphans/Zombies=0
```

### State File Corruption

**Cause**: Unexpected shutdown or disk full

**Symptoms**: Bot fails to start or crashes during state load

**Solution**:
```bash
# Clear corrupted state
rm -rf state/*.json
rm -rf persistence/*.json

# Restart bot (will start fresh)
```

---

## Circuit Breaker Issues

### Circuit Breaker OPEN (Persistent)

**Symptoms**:
```
🚨 Circuit breaker 'rest_market_data' is OPEN. Retry after 58.3s
```

**Cause**: >5 consecutive API failures

**Diagnosis**:
```bash
# Check recent errors
grep "Circuit breaker" bot.log | tail

# Check API health
curl https://fapi.binance.com/fapi/v1/ping
```

**Solutions**:
1. Wait for auto-recovery (60 seconds)
2. Bot will use WebSocket cache during outage
3. If persists >5 minutes, check Binance status page
4. Manually reset: restart bot

---

## Logging Issues

### Log File Too Large

**Cause**: Long runtime without rotation

**Solution**:
```bash
# Enable log rotation in .env
LOG_ROTATION=true
LOG_MAX_SIZE=50  # MB

# Manual cleanup
truncate -s 0 bot.log
# Or
rm redo_round_1_v*.log
```

### Excessive "Tick" Logs

**Cause**: DEBUG log level

**Solution**:
```bash
# Change log level
# Edit .env
LOG_LEVEL=INFO  # Was DEBUG

# Or filter logs
tail -f bot.log | grep -v "⚡ Tick"
```

---

## Emergency Procedures

### Bot Frozen / Not Responding

**Diagnosis**:
```bash
# Check if process still alive
ps aux | grep main.py

# Check recent logs
tail -n 100 bot.log
```

**Solution**:
```bash
# Force shutdown
pkill -9 -f main.py

# Clean exchange (important!)
python sweep_exchange.py --symbol MULTI

# Restart bot
```

### Runaway Losses

**Immediate Action**:
```bash
# 1. Kill bot (don't move files, just kill)
pkill -9 -f main.py

# 2. Close all positions manually
python sweep_exchange.py --symbol MULTI

# 3. Review logs
grep "Position closed" bot.log | tail -20

# 4. Investigate before restarting
python state_audit.py --symbol MULTI
```

---

## Configuration Validation

### Verify Environment

```bash
# Check Python version
python --version

# Check installed packages
pip list | grep -E "(aiohttp|asyncio|prometheus)"

# Verify .env
cat .env | grep -v "^#" | grep "="
```

### Test Exchange Connection

```bash
# Create test_connection.py
cat << 'EOF' > test_connection.py
import asyncio
from exchanges.connectors.binance import BinanceNativeConnector

async def test():
    conn = BinanceNativeConnector(mode="demo")
    await conn.connect()
    balance = await conn.fetch_balance()
    print(f"✅ Connected! Balance: {balance.get('total', {}).get('USDT', 0)} USDT")
    await conn.disconnect()

asyncio.run(test())
EOF

# Run test
python test_connection.py
```

---

## Getting Help

If issues persist after troubleshooting:

1. **Collect Debug Info**:
```bash
# System info
uname -a
python --version
pip list > requirements_installed.txt

# Recent logs
tail -n 500 bot.log > debug_logs.txt

# State audit
python state_audit.py --symbol MULTI > audit_report.txt
```

2. **File GitHub Issue**:
   - Include debug_logs.txt
   - Include audit_report.txt
   - Describe steps to reproduce
   - Redact API keys!

3. **Join Community**:
   - Discord: [invite_link]
   - GitHub Discussions

---

## Common Error Codes Reference

| Code | Meaning | Action |
|------|---------|--------|
| -1001 | Disconnected | Automatic reconnect |
| -1003 | Too many requests | Rate limiter handles |
| -1015 | Too many orders | Reduce frequency |
| -2011 | Unknown order | Order already filled/canceled |
| -2013 | Order doesn't exist | Ignore (already gone) |
| -2019 | Margin insufficient | Increase balance |
| -2021 | Order would trigger | Price too close to market |
| -4003 | Quantity too small | Increase bet size |
| -4164 | Notional too small | Increase bet size or leverage |

---

For more information:
- [README.md](README.md) - Getting started
- [CONFIGURATION.md](CONFIGURATION.md) - Settings reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
