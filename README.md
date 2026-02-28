# Casino-V3 🎰⚡

> **High-frequency algorithmic trading bot for cryptocurrency futures**
> Built with Python, asyncio, and native exchange integrations

[![v4.3.0-hft-stable](https://img.shields.io/badge/version-v4.3.0--hft--stable-brightgreen.svg)](https://github.com/chesterbelle/Casino-V3/releases/tag/v4.3.0-hft-stable)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---

## 🚀 Features

### Core Trading
- **Multi-Strategy Execution** - Adaptive player with 50+ technical indicators
- **OCO (One-Cancels-Other) Brackets** - Automatic TP/SL placement
- **Position Management** - Intelligent entry/exit with trailing stops
- **Multi-Symbol Support** - Trade up to 50+ symbols simultaneously
- **Risk Management** - Dynamic position sizing and leverage control

### Resilience & Reliability
- **Circuit Breakers** - Automatic REST API failover to WebSocket
- **Error Classification** - Smart retry logic for transient failures
- **Graceful Shutdown** - Clean position closure on timeout/signal
- **State Recovery** - Automatic state persistence and restoration
- **Watchdog Monitoring** - Task-level health checks and stall detection

### Performance (Phase 310 Validated)
- **5.4ms Tick-to-Order Latency** - Sub-10ms decision-to-wire pipeline
- **3ms TP/SL Parallelism** - Near-simultaneous bracket placement
- **$0.00 Error Leakage** - Zero infrastructure errors affecting PnL
- **Native Exchange Integration** - Direct Binance Futures API (no CCXT overhead)
- **WebSocket-First Architecture** - Real-time market data with minimal latency
- **Async-First Design** - Non-blocking I/O with asyncio and aiohttp

### Observability
- **Prometheus Metrics** - Comprehensive performance and business metrics
- **Structured Logging** - Detailed operational logs with context
- **State Auditing** - Real-time exchange state reconciliation
- **Session Reporting** - Automated trade summaries and P&L reports

---

## 📋 Prerequisites

- **Python**: 3.13 or higher
- **OS**: Linux (tested on Ubuntu 22.04+)
- **Exchange**: Binance Futures account (Testnet or Live)
- **API Keys**: Binance API key with futures trading permissions

---

## ⚡ Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/Casino-V3.git
cd Casino-V3
```

### 2. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Binance API credentials
nano .env
```

**Required Variables:**
```env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
EXCHANGE_MODE=demo  # or 'live' for production
```

### 4. Run the Bot
```bash
# Single symbol (recommended for testing)
python main.py --symbol BTC/USDT --mode demo --bet-size 0.05

# Multi-symbol mode (advanced)
python main.py --symbol MULTI --mode demo --bet-size 0.05 --timeout 150
```

### 5. Monitor Metrics (Optional)
```bash
# Metrics available at http://localhost:8000/metrics
curl http://localhost:8000/metrics
```

---

## Architecture (V4 Reactor)

Casino-V3 uses a Clock-Reactor architecture with event-driven execution:

```
main.py (Orchestrator & Clock Reactor)
  |
  +-- ClockReactor ------> Tick Events -------> SensorManager (50+ indicators)
  |                                             +-> SignalAggregator (consensus)
  |
  +-- Croupier V4 -------> OCOManager --------> Bracket Execution (3ms gap)
  |                       +-> PositionTracker    +-> ExitManager (Shadow SL)
  |                       +-> ReconciliationWorker
  |
  +-- ExchangeAdapter ---> BinanceNativeConnector (100% Native)
  |                       +-> 4 Ingestion Shards (WebSocket)
  |                       +-> Execution Airlock (IPC)
  |                       +-> User Data Sentinel
  |
  +-- Resilience --------> ErrorHandler + CircuitBreaker
                          +-> PortfolioGuard (drawdown protection)
                          +-> Watchdog (stall detection)
```

---

## 🎯 Usage Examples

### Single Symbol Trading
```bash
# BTC with 0.1 USDT bet size, auto-close on exit
python main.py --symbol BTC/USDT --mode demo --bet-size 0.1 --close-on-exit
```

### Multi-Symbol with Timeout
```bash
# Trade 50 symbols for 150 minutes, close positions on timeout
python main.py --symbol MULTI --mode demo --bet-size 0.05 --timeout 150 --close-on-exit
```

### Validation Pipeline
```bash
# Run the full 4-layer validation pipeline
# Layer 1: Preflight | Layer 2: Concurrency | Layer 3: Latency | Layer 4: Chaos
python -m utils.validators.trading_flow_validator --mode demo
python -m utils.validators.multi_symbol_validator --mode demo --size 500
python -m utils.validators.hft_latency_benchmark --mode demo --iterations 3
python -m utils.validators.multi_symbol_chaos_tester --mode demo --duration 300
```

### Reset State
```bash
# Clean all session data for a fresh start
python reset_data.py
```

---

## 📊 Configuration

For detailed configuration options, see [CONFIGURATION.md](CONFIGURATION.md).

**Key Settings:**
- `--symbol`: Symbol to trade (`BTC/USDT`, `MULTI`, etc.)
- `--mode`: Trading mode (`demo` for testnet, `live` for production)
- `--bet-size`: Base position size in USDT
- `--timeout`: Auto-shutdown timeout in minutes
- `--close-on-exit`: Close all positions on shutdown

---

## 🐛 Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

**Quick Fixes:**
- **Port 8000 in use**: Kill existing process or change metrics port
- **API errors**: Verify API keys and permissions
- **WebSocket disconnects**: Check network stability and firewall rules
- **Cache misses**: Adjust `threshold_ms` in `exchange_adapter.py` (default: 60s)

---

## 🧪 Testing

```bash
# Run unit tests
pytest tests/

# Run with coverage
pytest --cov=. tests/

# Integration tests
pytest tests/integration/
```

---

## 📈 Monitoring

### Prometheus Metrics
Casino-V3 exposes metrics on `http://localhost:8000/metrics`:

- `casino_positions_open_total` - Open positions by symbol/side
- `casino_trades_total` - Total trades executed
- `casino_order_execution_duration_seconds` - Order latency
- `casino_api_errors_total` - API errors by category

### Grafana Dashboard
Import the example dashboard from `monitoring/grafana-dashboard.json`

---

## 🔒 Security Best Practices

1. **Never commit `.env` files** - Use `.env.example` as template
2. **Use testnet for development** - Set `EXCHANGE_MODE=demo`
3. **Restrict API permissions** - Enable only futures trading, no withdrawals
4. **IP whitelist** - Add your IP to Binance API key restrictions
5. **Rotate keys regularly** - Generate new API keys every 90 days

---

## 🚧 Development

### Code Style
```bash
# Format code
black .
isort .

# Lint
flake8 .
```

### Pre-commit Hooks
```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details

---

## 🙏 Acknowledgments

- Binance for robust API documentation
- Python asyncio community for async best practices
- Contributors who helped test and improve stability

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/Casino-V3/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/Casino-V3/discussions)
- **Email**: support@example.com

---

**⚠️ Disclaimer**: This software is for educational purposes. Trading cryptocurrencies carries risk. Never trade with funds you cannot afford to lose.
