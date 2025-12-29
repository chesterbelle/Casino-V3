<!-- Copilot / AI agent instructions for the Casino-V2 codebase -->
# Casino-V2 — Copilot Instructions

These instructions give an AI coding agent the minimal, high-value context
to be productive in this repository. They are intentionally concise and
refer to exact files and patterns in the codebase.

1) Big picture
- Purpose: Casino-V2 is a unified trading system supporting backtest, demo
  and live modes. The single entry point is `main.py` which wires a
  `TradingSession`, a `DataSource` and a `Player` strategy.
- State ownership: `Croupier` (in `croupier/croupier.py`) is the canonical
  portfolio controller — it "owns" balance and positions. `PositionTracker`
  (under `core/portfolio`) is the bot's source of truth for open positions.
- Exchange abstraction: Adapters live in `exchanges/adapters/*` and connectors
  in `exchanges/connectors/*`. Adapters are expected to be stateless; the
  Croupier delegates all order execution to the exchange adapter.

2) Critical files & where to look
- Entry point: `main.py` — run modes, CLI flags, and result saving.
Core logging & utilities: `core/logger.py`, `core/config.py`.
- State & control: `croupier/croupier.py` (central business logic),
  `core/portfolio/balance_manager.py`, `core/portfolio/position_tracker.py`.
- Connectors & adapters: `exchanges/adapters/` and `exchanges/connectors/` —
  adapter methods used by Croupier: `execute_order`, `cancel_order`,
  `fetch_order`, `fetch_open_orders`, `fetch_positions`, `get_current_price`.
- Configs: `config/` (modular) — `system`, `trading`, `strategy`, `exchange`.

3) Key design patterns & conventions
- Croupier is state owner: prefer updating `BalanceManager` and
  `PositionTracker` instead of mutating exchange state directly.
- OCO / TP-SL flow: Croupier creates a main order and then sets TP/SL
  via `_setup_oco_orders`. Adapters should handle exchange-specific params
  (e.g. `stopPrice`, `reduceOnly`, `positionSide`). See `croupier`'s
  `_setup_oco_orders` and `_handle_position_closure` for expectations.
- Backtest data: when running backtests any input timeframe is forced to
  `1m` (see `main.py` and BacktestDataSource creation).
- Safety-first: many methods include defensive checks (e.g. minimum
  notional, `insufficient_funds` rejection). Preserve these checks.
- Ghost mode: orders with `ghost=True` should not touch balance (used for
  training/experiments). The `order` dict contract is documented in
  `croupier/croupier.py` header.

4) Developer workflows (commands discoverable in repo)
- Run backtest (example):
  `python main.py --mode=backtest --player=paroli --data=path/to.csv --initial-balance=10000.0`
- Run demo/live: adjust `--mode=demo|live` and provide `--symbol` & `--interval`.
- Tests: project uses `pytest` settings from `pyproject.toml`. Run tests with:
  `pytest -q` or `python -m pytest`.
- Formatting / linting / static analysis (configs in `pyproject.toml`):
  - `black` (line-length=120), `flake8`, `mypy` (strict rules). Run them
    if requested by maintainers.

5) What to change (and what not to change)
- Safe changes: small refactors within a module, clarifying docstrings,
  adding unit tests under `tests/` that target a single module.
- Risky changes: altering the Croupier ownership model, changing the
  PositionTracker semantics, or modifying adapter contracts without updating
  all connectors. If a change touches exchanges/ adapters, test live/demo
  flows first (or add mocks).

6) Useful examples / snippets
- Instantiate croupier (used throughout):
  `from croupier.croupier import Croupier`
  `c = Croupier(exchange_adapter, initial_balance=10000.0)`
- Public Croupier API to use in patches/tests:
  `get_balance(), get_equity(), get_open_positions(), get_portfolio_state(), execute_order(order)`

7) Notes for AI edits
- Preserve Spanish-language logging/docstrings and emoji markers unless the
  maintainer asks for translation — logs are part of developer UX.
- When adding functionality that affects live orders, prefer adding a
  feature flag or `ghost`-style toggle and thorough unit tests.
- Use existing helpers: e.g. `ExchangeStateSync`, `BalanceManager`, and
  `PositionTracker` rather than reimplementing state logic.

If any of these points are unclear or you want more detail in a specific
area (connectors, adapters, portfolio internals, or testing setup), tell
me which area to expand and I'll iterate.
