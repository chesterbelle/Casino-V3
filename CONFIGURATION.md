# Configuration Guide 🔧

This document describes all configuration options for Casino-V3.

---

## Environment Variables

### Required Variables

#### Exchange Credentials
```env
# Binance API credentials
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# Exchange mode: 'demo' (testnet) or 'live' (production)
EXCHANGE_MODE=demo
```

### Optional Variables

#### Trading Configuration
```env
# Default leverage for futures positions (1-125)
DEFAULT_LEVERAGE=10

# Maximum number of concurrent positions
MAX_POSITIONS=10

# Base position size in USDT
BASE_BET_SIZE=0.05

# Risk percentage per trade (0.01 = 1%)
RISK_PER_TRADE=0.02
```

#### API & Networking
```env
# Request timeout for REST API calls (seconds)
API_TIMEOUT=30

# WebSocket ping interval (seconds)
WS_PING_INTERVAL=20

# Rate limit buffer percentage (0.8 = use 80% of limit)
RATE_LIMIT_BUFFER=0.8
```

#### Logging
```env
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log file path
LOG_FILE=bot.log

# Enable log rotation (true/false)
LOG_ROTATION=true

# Max log file size before rotation (MB)
LOG_MAX_SIZE=50
```

#### Monitoring
```env
# Prometheus metrics server port
METRICS_PORT=8000

# Enable metrics server (true/false)
ENABLE_METRICS=true
```

#### Performance
```env
# Number of sensor worker processes
SENSOR_WORKERS=4

# WebSocket subscription batch size
WS_BATCH_SIZE=10

# Ticker cache TTL (seconds)
TICKER_CACHE_TTL=3
```

---

## Command Line Arguments

### Core Arguments

#### --symbol
**Description**: Trading symbol or mode
**Type**: String
**Examples**:
- `BTC/USDT` - Trade Bitcoin futures
- `ETH/USDT` - Trade Ethereum futures
- `MULTI` - Trade top 50 symbols simultaneously

```bash
python main.py --symbol BTC/USDT
python main.py --symbol MULTI
```

#### --mode
**Description**: Trading mode
**Type**: String
**Values**: `demo`, `live`
**Default**: `demo`

```bash
python main.py --mode demo  # Binance Testnet
python main.py --mode live  # Binance Production
```

#### --bet-size
**Description**: Base position size in USDT
**Type**: Float
**Default**: `0.05`
**Range**: `0.01` - `1000`

```bash
python main.py --bet-size 0.1  # 0.1 USDT per position
```

### Optional Arguments

#### --timeout
**Description**: Auto-shutdown timeout in minutes
**Type**: Integer
**Default**: None (runs indefinitely)

```bash
python main.py --timeout 150  # Stop after 150 minutes
```

#### --close-on-exit
**Description**: Close all positions on shutdown
**Type**: Flag (no value needed)
**Default**: False

```bash
python main.py --close-on-exit
```

#### --leverage
**Description**: Leverage multiplier
**Type**: Integer
**Default**: `10`
**Range**: `1` - `125`

```bash
python main.py --leverage 20
```

---

## Configuration Files

### .env File

Create a `.env` file in the project root:

```env
# Exchange
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
EXCHANGE_MODE=demo

# Trading
DEFAULT_LEVERAGE=10
MAX_POSITIONS=10
BASE_BET_SIZE=0.05

# Logging
LOG_LEVEL=INFO
LOG_FILE=bot.log

# Metrics
METRICS_PORT=8000
ENABLE_METRICS=true
```

### symbols.json (MULTI Mode)

When using `--symbol MULTI`, the bot reads from `config/symbols.json`:

```json
{
  "active_symbols": [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT"
  ],
  "max_symbols": 50,
  "min_volume_24h": 1000000
}
```

---

## Exchange-Specific Settings

### Binance Futures

#### API Endpoints
- **Testnet**: `https://testnet.binancefuture.com`
- **Production**: `https://fapi.binance.com`

#### Rate Limits
Casino-V3 automatically respects Binance rate limits:

| Endpoint Type | Limit | Buffer Used |
|---------------|-------|-------------|
| Orders | 1200/min | 960/min (80%) |
| Account | 600/min | 480/min (80%) |
| Market Data | 6000/min | 4800/min (80%) |

#### WebSocket Streams
Maximum concurrent connections: **200 streams**

---

## Advanced Configuration

### Circuit Breaker Settings

Edit in `core/error_handling/circuit_breaker.py`:

```python
CircuitBreaker(
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=60,      # Try recovery after 60s
    half_open_max_calls=3    # Allow 3 test calls in HALF_OPEN
)
```

### Retry Configuration

Edit in `core/error_handling/error_handler.py`:

```python
RetryConfig(
    max_retries=3,           # Maximum retry attempts
    backoff_base=1.0,        # Initial backoff (seconds)
    backoff_max=60.0,        # Maximum backoff (seconds)
    backoff_factor=2.0,      # Exponential factor
    jitter=True              # Add randomness to backoff
)
```

### State Persistence

Edit in `core/state/persistent_state.py`:

```python
PersistentState(
    save_interval=5.0,       # Save every 5 seconds
    backup_count=10,         # Keep 10 backup files
    use_compression=False    # Disable JSON compression
)
```

---

## Environment Profiles

### Development

```env
EXCHANGE_MODE=demo
LOG_LEVEL=DEBUG
ENABLE_METRICS=true
MAX_POSITIONS=5
BASE_BET_SIZE=0.05
```

### Production

```env
EXCHANGE_MODE=live
LOG_LEVEL=INFO
ENABLE_METRICS=true
MAX_POSITIONS=20
BASE_BET_SIZE=1.0
LOG_ROTATION=true
```

### Testing

```env
EXCHANGE_MODE=demo
LOG_LEVEL=DEBUG
ENABLE_METRICS=false
MAX_POSITIONS=1
BASE_BET_SIZE=0.01
```

---

## Validation

Before running, validate your configuration:

```bash
# Check environment variables
python -c "from config import *; print('✅ Config valid')"

# Test API connection
python test_connection.py

# Verify .env file
cat .env | grep -v "^#" | grep -v "^$"
```

---

## Security Checklist

- [ ] API keys stored in `.env`, not committed to git
- [ ] `.env` added to `.gitignore`
- [ ] API keys have proper permissions (futures only, no withdrawals)
- [ ] IP whitelist configured on Binance
- [ ] Using testnet for development (`EXCHANGE_MODE=demo`)
- [ ] Log files excluded from version control
- [ ] Metrics port (8000) not exposed to internet

---

## Troubleshooting

### Issue: "API key not found"
**Solution**: Ensure `.env` file exists and contains valid `BINANCE_API_KEY`

### Issue: "Permission denied on futures endpoints"
**Solution**: Enable futures trading permission in Binance API key settings

### Issue: "Port 8000 already in use"
**Solution**: Change `METRICS_PORT` or kill existing process using port 8000

### Issue: "Rate limit exceeded"
**Solution**: Reduce `RATE_LIMIT_BUFFER` or decrease trading frequency

---

## Best Practices

1. **Use testnet first** - Always test with `EXCHANGE_MODE=demo`
2. **Start small** - Begin with `BASE_BET_SIZE=0.05` or lower
3. **Monitor metrics** - Enable Prometheus metrics for observability
4. **Rotate logs** - Enable `LOG_ROTATION` to prevent disk space issues
5. **Limit positions** - Set conservative `MAX_POSITIONS` initially
6. **Use timeouts** - Always set `--timeout` for endurance runs

---

For more information, see:
- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
