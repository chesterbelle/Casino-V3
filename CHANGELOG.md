# Changelog 📝

All notable changes to Casino-V3 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added (v2.4 - Documentation & Optimization)
- Comprehensive README.md with quick start and features
- CONFIGURATION.md with all environment variables
- ARCHITECTURE.md with system design diagrams
- TROUBLESHOOTING.md with common issues and solutions
- CHANGELOG.md (this file)

---

## [2.3.1] - 2025-12-28

### Fixed - Chaos Endurance Round 1 Completion
- **OCOManager Lock Leakage**: Fixed `pending_symbols` not releasing on price fetch failures
- **RateLimiter Timeouts**: Added 45s safety timeout to prevent indefinite waits
- **Connector Disconnect Timing**: Moved disconnect after `emergency_sweep` to prevent HTTP session closure
- **ErrorClassifier**: Added explicit handling for `CancelledError` and `TimeoutError`
- **Shutdown Sequence**: Reordered to stop sensors/engine before sweep for clean environment
- **Emergency Sweep**: Hardened with `return_exceptions=True` to prevent cascading failures

### Verified
- ✅ Chaos Endurance Round 1 v4: 134 trades, 150 minutes, **53/53 positions closed cleanly**
- ✅ Zero residuals on exchange (audit confirmed)
- ✅ 51 debounce events handled without permanent locks

---

## [2.3.0] - 2025-12-26

### Added - Global Circuit Breaker & Panic Mode
- **GlobalCircuitBreaker**: REST endpoint health monitoring
- **WS-Only Panic Mode**: Automatic REST-to-WebSocket failover during latency
- **Bulk Order Cancellation**: `cancel_all_orders()` for efficient emergency sweeps
- **Shutdown Reporting Priority**: Moved session report before component stops

### Changed
- Increased `aiohttp` session timeouts from 10s to 30s globally
- Increased bulk ticker cache TTL from 1s to 3s
- Refactored `main.py` shutdown sequence for better reporting

### Verified
- ✅ Phase 24: Automatic REST-to-WS failover during simulated latency
- ✅ Phase 25 Prep: Exchange cleanup and bulk operations

---

## [2.2.0] - 2025-12-24

### Added - Task-Level Watchdog System
- **WatchdogRegistry**: Centralized task monitoring with configurable timeouts
- **Heartbeat Integration**: All critical loops now signal progress
  - StateManager persistent save loop
  - ReconciliationService reconciliation loop
  - Engine processing loop
  - Main.py ticker tasks

### Changed
- **ThreadPoolExecutor** in `PersistentState` for non-blocking I/O
- Moved JSON serialization to executor threads

### Verified
- ✅ Phase 21: Watchdog system detects stalled tasks
- ✅ Phase 22: 150-minute stability run with heartbeat monitoring
- ✅ Phase 23: High-load I/O without blocking

---

## [2.1.0] - 2025-12-22

### Added - Resilience Hardening
- **CircuitBreaker Improvements**: Selective error recording (validation errors don't trip breaker)
- **Ticker Timeout Resilience**: Per-request timeout overrides for bulk operations
- **Parallel Graceful Shutdown**: TP/SL cancellation in parallel, position closure with semaphore
- **HeartbeatWatchdog**: Progress monitoring during shutdown

### Fixed
- **Non-unique Adoption IDs**: Added timestamp to prevent ID collisions
- **Short Position Detection**: Fixed negative size interpretation for shorts
- **CircuitBreaker Stagnation**: Validation errors now count as "proof of life"

### Verified
- ✅ Phase 17: Reduced "Connection timeout" errors to zero
- ✅ Phase 18: Clean shutdown with 48 positions (0 residuals)

---

## [2.0.5] - 2025-12-20

### Added - Reconciliation & Sync Hardening
- **Batch Sync**: `reconcile_all()` for bulk position adoption
- **Symbol Normalization**: Consistent symbol format across all components
- **Reverse Ghost Prevention**: Fixed "Naked" position formation

### Fixed
- **ExchangeAdapter Symbol Shadowing**: Resolved `None` vs `"MULTI"` conflicts
- **Fetch Positions Filtering**: Corrected open position detection logic

### Verified
- ✅ Phase 15: Reverse Ghost resolution (100% audit clean)

---

## [2.0.4] - 2025-12-18

### Added - Performance Optimizations
- **Bulk REST Ticker Fetching**: `fetch_tickers()` reduces weight from 40 to 1
- **Ticker Cache**: 1-second TTL cache for bulk tickers
- **Asyncio Lock**: Prevents concurrent bulk fetches
- **Rate Limit Differentiation**: Separate limits for orders, account, market data
- **aiohttp Tuning**: Increased connector limits and timeouts

### Verified
- ✅ Phase 13: Weight reduction verified (40→1 for 40 symbols)
- ✅ Phase 14: 15-minute candle turn stability

---

## [2.0.3] - 2025-12-16

### Added - Subscription Management
- **Batch Subscription Worker**: Queue-based batching and throttling
- **High-Load Performance**: Tested with 40+ symbols

### Verified
- ✅ Phase 11: High-scale subscription verified

---

## [2.0.2] - 2025-12-14

### Added - Symbol Normalization
- **`normalize_symbol()` Utility**: Handles various symbol formats
- **StreamManager Integration**: All symbols normalized before subscription
- **Croupier Integration**: Position tracking with normalized symbols

### Fixed
- **Orphan Prevention**: Symbol format mismatches causing orphaned positions

### Verified
- ✅ Phase 9: MULTI mode with zero orphans

---

## [2.0.1] - 2025-12-12

### Fixed - Resilience Core
- **Global Stutter**: Moved `fetch_balance()` out of blocking IPC in SensorManager
- **CancelledError Handling**: Proper exception handling in ErrorHandler for circuit breakers
- **Stream Timeout**: Disabled symbols on persistent `TimeoutError`

### Verified
- ✅ Phase 6: Resilience hardening
- ✅ Phase 7: 1-hour stability run

---

## [2.0.0] - 2025-12-10

### Added - Casino-V3 Rewrite
- **Native Exchange Integration**: Direct Binance API (removed CCXT)
- **WebSocket-First Architecture**: Real-time market data and user updates
- **OCOManager**: Automated bracket orders (Entry + TP + SL)
- **PositionTracker**: Full position lifecycle management
- **ErrorHandler**: Intelligent retry with exponential backoff
- **CircuitBreaker**: Automatic failover on service degradation
- **State Recovery**: Automatic persistence and crash recovery
- **Multiprocessing Sensors**: Parallel signal computation

### Changed
- Complete architectural overhaul from V2
- Async-first design with asyncio
- Event-driven component communication

### Removed
- CCXT dependency (complete native implementation)

---

## Migration Guides

### v2.3.x → v2.4.x (Documentation Update)
- **No code changes** - Only documentation enhancements
- Review new docs: README.md, CONFIGURATION.md, ARCHITECTURE.md
- **Action Required**: None

### v2.2.x → v2.3.x (Shutdown Fixes)
- **Breaking**: Engine no longer disconnects connector in `stop()`
- **Action Required**: Ensure `main.py` shutdown sequence includes explicit `adapter.disconnect()`
- **Migration**: Already handled in updated `main.py`

### v2.1.x → v2.2.x (Watchdog System)
- **New Feature**: WatchdogRegistry for task monitoring
- **Action Required**: None (auto-integrated)
- **Optional**: Add custom heartbeats to new background tasks

### v2.0.x → v2.1.x (Resilience)
- **New Feature**: Enhanced circuit breakers
- **Action Required**: None (backward compatible)
- **Optional**: Review new timeout settings in `CONFIGURATION.md`

---

## Deprecation Notices

### v2.4
- None

### v2.3
- **Removed**: `Engine.stop()` no longer calls `data_feed.disconnect()`
  - **Reason**: Premature disconnect prevented emergency sweep
  - **Replacement**: Explicit disconnect in `main.py` shutdown

---

## Upcoming Features (Roadmap)

### v2.5 - Logging & Metrics Enhancements
- Configurable log levels
- Log rotation policies
- Additional Prometheus metrics
- Grafana dashboard examples

### v2.6 - Code Quality
- Unit test suite (pytest)
- Integration tests
- CI/CD pipeline (GitHub Actions)
- Code coverage reporting

### v3.0 - Multi-Exchange Support
- OKX connector
- Bybit connector
- Unified exchange adapter
- Cross-exchange arbitrage

---

## Support

For issues or questions about specific versions:
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- File issues on [GitHub](https://github.com/yourusername/Casino-V3/issues)
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for design details
