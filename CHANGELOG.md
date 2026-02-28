# Changelog 📝

All notable changes to Casino-V3 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [4.3.0] - 2026-02-28

### Performance - HFT Latency Compression (Phase 310)
- **Tick-to-Order (T0-T2)**: Compressed from 551ms to **5.4ms** (100x improvement)
- **Signal Aggregation (T0-T1)**: 3.9ms avg (was 140ms, `SIGNAL_TIMEOUT_MS` 500→20ms)
- **Signal-to-Wire (T1-T2)**: 1.5ms avg (was 411ms, eliminated REST fallbacks)
- **TP/SL Parallelism Gap**: 3ms (was 10ms in Phase 240)
- **Error Recovery**: $0.00 (0 error trades across 150-min stress test)

### Changed
- `exchange_adapter.py`: WS cache staleness threshold extended to 60s (was 1.5s)
- `aggregator.py`: `SIGNAL_TIMEOUT_MS` compressed from 500ms to 20ms
- `.gitignore`: Hardened to prevent future log/data leakage

### Removed - Repo Cleanup
- Removed 19 debug/one-off scripts from root directory
- Removed 4 v4.2.0 backup files (preserved in git history)
- Removed 3 strategy backup copies
- Removed 16 stale log/report text dumps
- Updated all documentation to v4.3.0

### Verified
- ✅ 150-minute stress test: 74 trades, $0.00 error leakage
- ✅ 4-layer validation pipeline: Preflight, Concurrency, Latency (3ms), Chaos
- ✅ 100% Healing Efficiency (11/11 positions saved)
- ✅ 100% WebSocket integrity (0 unmatched events)

---

## [4.2.0] - 2026-02-22

### Added - Phase 240 HFT Optimizations
- **Execution Airlock**: IPC-based order execution via multiprocessing
- **4 Ingestion Shards**: Parallel WebSocket ingestion workers
- **Bulk Ticker Optimization**: Batch REST fallback for cache misses
- **TP/SL Parallelism**: Near-simultaneous bracket placement (10ms gap)

### Verified
- ✅ Phase 240: HFT benchmark passing all targets

---

## [4.1.0] - 2026-02-17

### Added - Phase 160 Resilience
- **Healing System**: Automatic orphan recovery with grace periods
- **Shadow SL**: In-memory stop-loss monitoring for rapid exit
- **Dynamic Drain**: 4-stage progressive exit (OPTIMISTIC→PANIC)
- **PortfolioGuard**: Drawdown protection with error caps

### Verified
- ✅ Phase 160: 100% healing efficiency, <2% orphan hygiene

---

## [4.0.0] - 2026-01-15

### Added - V4 Reactor Architecture
- **Clock Reactor**: Event-driven tick processing
- **Croupier V4**: Unified order lifecycle management
- **ReconciliationWorker**: Async exchange-state synchronization
- **TradeHistorian**: Persistent SQLite trade database

---

## [2.3.1] - 2025-12-28

### Fixed - Chaos Endurance Round 1 Completion
- **OCOManager Lock Leakage**: Fixed `pending_symbols` not releasing on price fetch failures
- **RateLimiter Timeouts**: Added 45s safety timeout to prevent indefinite waits
- **Connector Disconnect Timing**: Moved disconnect after `emergency_sweep`
- **Emergency Sweep**: Hardened with `return_exceptions=True`

### Verified
- ✅ 134 trades, 150 minutes, **53/53 positions closed cleanly**

---

## [2.0.0] - 2025-12-10

### Added - Casino-V3 Rewrite
- Native Exchange Integration (removed CCXT)
- WebSocket-First Architecture
- OCOManager, PositionTracker, ErrorHandler, CircuitBreaker
- Multiprocessing Sensors

---

## Stable Version Tags

| Tag | Date | Highlights |
|:----|:-----|:-----------|
| `v4.3.0-hft-stable` | 2026-02-28 | 5.4ms T0-T2, $0.00 errors |
| `v4.2.0-throughput-optimized` | 2026-02-22 | Execution Airlock, 4 shards |
| `v4.1.0-resilience-stable` | 2026-02-17 | Healing, Shadow SL, Drain |
| `v4.0.0-beta-stable` | 2026-01-15 | V4 Reactor Architecture |
