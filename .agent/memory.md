# Casino-V3 Agent Memory

## Project Overview
**Casino-V3** is an automated cryptocurrency futures trading bot for Binance Futures (Testnet/Live).

## Key Architecture

### Core Components
| Component | Purpose |
|-----------|---------|
| `Engine` | Signal processing & trade decision-making |
| `Croupier` | Trade execution orchestrator |
| `PositionTracker` | Active position management |
| `OCOManager` | Stop-loss/Take-profit order management |
| `BinanceNativeConnector` | Exchange API interface (REST + WebSocket) |
| `Historian` | SQLite-based trade persistence |
| `ErrorHandler` | Circuit breaker & retry logic |

### Key Files
- `main.py` - Entry point, orchestrates startup/shutdown
- `config/trading.py` - Trading configuration
- `config/strategies.py` - Strategy parameters
- `utils/symbol_norm.py` - Symbol normalization utility
- `state_audit.py` - Exchange state verification tool

## Operational Commands

### Run Bot
```bash
.venv/bin/python main.py --mode demo --symbol MULTI --timeout 150 --close-on-exit
```

### Reset State
```bash
.venv/bin/python reset_data.py
```

### Validate Architecture
```bash
.venv/bin/python -m utils.validators.multi_symbol_validator --mode demo --size 500
```

## Critical Success Metrics
- **Error Recovery = $0.00** (zero error trades)
- **Audit Adjust < $1.00** (minimal accounting drift)
- **Clean shutdown** (0 residual positions/orders)

## Known Gotchas
1. **Symbol Normalization**: Always use `normalize_symbol()` - inconsistent formats cause orphan positions
2. **Graceful Exit Timeout**: TP modifications can hang; use `GRACEFUL_TP_TIMEOUT`
3. **Bulk Ticker Cache**: 3s TTL to prevent REST rate limit hits
4. **Min Notional**: Bet size must exceed exchange minimums or trades skip silently

## Completed Milestones
- ✅ 31 Phases of stability hardening
- ✅ 150-minute endurance runs (Error Recovery = $0)
- ✅ Session-aware Historian (isolated accounting)
- ✅ Graceful shutdown with drain mode
- ✅ Full documentation suite

---
*Last Updated: 2026-01-19*
