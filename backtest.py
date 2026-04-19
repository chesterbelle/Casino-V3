"""
Casino V4 - Microstructure Backtester
High-fidelity historical simulation using the Clock Reactor.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Phase 1850: Simulation Time Interceptor
# Ensures that all components using time.time() (SetupEngine, Historian)
# receive the historical tick timestamp instead of wall-clock time.
SIM_TIME = 0.0
_original_time = time.time


def sim_time_provider():
    return SIM_TIME if SIM_TIME > 0 else _original_time()


time.time = sim_time_provider

# Add root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config.trading as trading_config  # noqa: E402
from core.backtest_feed import BacktestFeed  # noqa: E402
from core.candle_maker import CandleMaker  # noqa: E402
from core.clock import Clock  # noqa: E402
from core.context_registry import ContextRegistry  # noqa: E402
from core.engine import Engine  # noqa: E402
from core.events import AggregatedSignalEvent, EventType, TickEvent  # noqa: E402
from core.execution import OrderManager  # noqa: E402
from core.sensor_manager import SensorManager  # noqa: E402
from croupier.croupier import Croupier  # noqa: E402
from decision.setup_engine import SetupEngineV4  # noqa: E402
from exchanges.adapters import ExchangeAdapter  # noqa: E402
from exchanges.connectors.virtual_exchange import VirtualExchangeConnector  # noqa: E402
from players.adaptive import AdaptivePlayer  # noqa: E402

# Setup logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Backtest-V4")


def parse_args():
    parser = argparse.ArgumentParser(description="Casino V4 Backtester")
    parser.add_argument("--data", type=str, required=True, help="Path to historical CSV/Parquet file")
    parser.add_argument("--symbol", type=str, default="BTC/USDT:USDT", help="Symbol to backtest")
    parser.add_argument("--balance", type=float, default=10000.0, help="Initial balance")
    parser.add_argument("--bet-size", type=float, default=0.01, help="Fixed bet size fraction")
    parser.add_argument("--delay", type=float, default=0.0, help="Artificial delay between events")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N events")
    parser.add_argument("--fast-track", action="store_true", help="Bypass warmup and RR limits for mechanical testing")
    parser.add_argument(
        "--depth-db", type=str, default=None, help="Path to Historian DB containing depth_snapshots (Phase 1300)"
    )
    parser.add_argument("--audit", action="store_true", help="Enable Zero-Interference Audit Mode (Edge Validation)")
    return parser.parse_args()


async def run_backtest():
    args = parse_args()

    if args.audit:
        trading_config.AUDIT_MODE = True
        trading_config.ENABLE_DECISION_TRACE = True
        logger.warning("🔍 AUDIT MODE ENABLED: Simulation will record signals and prices. Proactive exits DISABLED.")
        logger.warning("📝 DECISION TRACE ENABLED: Logic gates will be audited and recorded to DB.")

    if not os.path.exists(args.data):
        logger.error(f"❌ Data file not found: {args.data}")
        sys.exit(1)

    # 1. Initialize Components
    engine = Engine()
    clock = Clock(tick_size_seconds=1.0)

    # 2. Setup Virtual Exchange
    connector = VirtualExchangeConnector(  # noqa: E402
        initial_balance=args.balance, fee_rate=0.0006, maker_fee_rate=0.0002, slippage_rate=0.0001  # Taker
    )
    adapter = ExchangeAdapter(connector, symbol=args.symbol)

    # 3. Setup Feed
    feed = BacktestFeed(
        engine=engine,
        data_path=args.data,
        symbol=args.symbol,
        delay=args.delay,
        exchange_connector=connector,
        limit=args.limit,
        depth_db_path=args.depth_db,
    )

    # 4. Setup Execution Layer
    croupier = Croupier(exchange_adapter=adapter, initial_balance=args.balance, engine=engine)
    await connector.connect()

    # Phase 249: Connect VirtualExchange balance updates to BalanceManager for PortfolioGuard # noqa: E402
    def on_balance_update(balance: float, timestamp: float = None):
        croupier.balance_manager.set_balance(balance, timestamp=timestamp)

    connector.set_balance_update_callback(on_balance_update)

    # MONKEY-PATCH: Disable real-time services for backtest performance
    # This prevents the bot from trying to sync with a dummy exchange every 60s
    async def no_op_async(*args, **kwargs):
        pass

    croupier.drift_auditor.start = no_op_async
    croupier.drift_auditor.stop = no_op_async
    croupier.drift_auditor.tick = no_op_async
    croupier.reconciliation.reconcile_symbol = no_op_async
    croupier.reconciliation.reconcile_all = no_op_async

    # Disable Croupier periodic tasks (Balance/Funding sync)
    croupier._sync_balance = no_op_async
    croupier._sync_funding_fees = no_op_async

    await croupier.start()

    # Zero-Lag Structural Context Layer (Global Singleton)
    context_registry = ContextRegistry()  # noqa: E402
    sensor_mgr = SensorManager(engine)
    setup_engine = SetupEngineV4(engine, context_registry=context_registry, fast_track=args.fast_track)
    player = AdaptivePlayer(  # noqa: E402
        engine,
        croupier,
        fixed_pct=args.bet_size,
        context_registry=context_registry,
        fast_track=args.fast_track,
    )

    # 5.1 Candle Maker (Crucial for Regime Sensors)
    CandleMaker(engine, is_backtest=True)

    om = OrderManager(engine, croupier, player, setup_engine.tracker)
    await om.start()

    # 6. Subscribe Components
    async def on_tick_context(e):
        global SIM_TIME
        SIM_TIME = e.timestamp
        context_registry.on_tick(e.symbol, e.price, e.volume, e.side)

    async def on_tick_croupier(e):
        await croupier.exit_manager.on_tick(e)

    async def on_order_update_tracker(e):
        await croupier.position_tracker.handle_order_update(e)

    async def on_candle_context(e):
        context_registry.on_candle(e.symbol, e.high, e.low)

    engine.subscribe(EventType.TICK, on_tick_context)
    engine.subscribe(EventType.TICK, on_tick_croupier)
    engine.subscribe(EventType.CANDLE, on_candle_context)
    engine.subscribe(EventType.ORDER_UPDATE, on_order_update_tracker)
    engine.subscribe(EventType.SIGNAL, setup_engine.on_signal)

    # 6.5 Setup Audit Handlers
    from core.observability.historian import historian

    if trading_config.AUDIT_MODE:

        async def audit_signal_handler(event: AggregatedSignalEvent):
            historian.record_signal(
                timestamp=event.timestamp,
                symbol=event.symbol,
                side=event.side,
                setup_type=event.setup_type or "unknown",
                price=event.price,
                metadata=str(event.metadata),
                session_id=croupier.position_tracker.session_id,
            )

        engine.subscribe(EventType.AGGREGATED_SIGNAL, audit_signal_handler)

        last_sample_ts = {}

        async def audit_price_handler(event: TickEvent):
            now = event.timestamp
            symbol = event.symbol
            if symbol not in last_sample_ts or (now - last_sample_ts[symbol] >= trading_config.AUDIT_SAMPLING_FREQ):
                historian.record_price_sample(now, symbol, event.price)
                last_sample_ts[symbol] = now

        engine.subscribe(EventType.TICK, audit_price_handler)
        logger.info(f"🔍 Audit: Listeners connected (Freq: {trading_config.AUDIT_SAMPLING_FREQ}s)")

        # Phase 1850: Decision Trace Infrastructure (Capa de Hierro)
        engine.subscribe(EventType.DECISION_TRACE, historian.on_decision_trace)
        logger.info("📝 Audit: Decision Traces linked to DECISION_TRACE gates")

    # 6. Register reactor components
    clock.add_iterator(adapter)
    clock.add_iterator(croupier)

    logger.info(f"🏁 Starting Backtest: {args.symbol} | Data: {Path(args.data).name}")

    # Start clock in background
    asyncio.create_task(clock.start())

    # Run feed (this blocks until done)
    await feed.run()

    # Post-backtest cleanup
    engine.running = False

    # Stop clock properly
    await clock.stop()

    # Give tasks time to finish
    await asyncio.sleep(0.5)

    # 7. Force-close all open positions for accurate accounting
    closed_count = await connector.force_close_all_positions()
    if closed_count > 0:
        logger.info(f"🏁 Force-closed {closed_count} open positions at end of data.")

    # 8. Final Report (use free balance — all positions are now closed)
    stats = await connector.fetch_balance()
    final_balance = stats[connector.base_currency]["free"]
    total_pnl = final_balance - args.balance

    trades = connector._trades
    closed_trades = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in closed_trades if t["pnl"] > 0]

    # 8.5 Persist closed trades to Historian DB (Parity Infrastructure Fix)
    for ct in closed_trades:

        entry_price = float(ct.get("entry_price", 0.0))
        exit_price = float(ct.get("price", 0.0))
        side = ct.get("position_side", "LONG")
        fee = float(ct.get("fee", 0.0))
        pnl = float(ct.get("pnl", 0.0))
        exit_reason = ct.get("exit_reason", "VIRTUAL_CLOSE")
        trade_id = ct.get("gemini_trade_id") or ct.get("order", ct.get("id", ""))

        # Phase 800: Restore mechanical parity telemetry
        mkt_ts = float(ct.get("timestamp", 0))

        historian.record_trade(
            {
                "trade_id": trade_id,
                "symbol": ct.get("symbol", args.symbol),
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "fee": fee,
                "funding": 0.0,
                "qty": ct.get("amount", 0),
                "gross_pnl": ct.get("pnl", 0),
                "net_pnl": (ct.get("pnl") or 0) - (ct.get("fee") or 0),
                "exit_reason": exit_reason,
                "t0_signal_ts": ct.get("t0_signal_ts"),
                "t1_decision_ts": ct.get("t1_decision_ts"),
                "t2_submit_ts": ct.get("t2_submit_ts"),
                "t4_fill_ts": mkt_ts,
                "setup_type": ct.get("setup_type", "unknown"),
            }
        )
    if closed_trades:
        logger.info(f"💾 Historian: Persisted {len(closed_trades)} backtest trades to DB.")

    print("\n" + "=" * 60)
    print("📊 BACKTEST V4 RESULTS SUMMARY")
    print("=" * 60)
    print(f"Final Balance    : ${final_balance:,.2f}")
    print(f"PnL Total        : ${total_pnl:+.2f} ({(total_pnl/args.balance)*100:+.2f}%)")
    print(f"Total Trades     : {len(closed_trades)}")
    print(f"Win Rate         : {(len(wins)/len(closed_trades)*100) if closed_trades else 0:.1f}%")
    if closed_trades:
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in closed_trades if t["pnl"] <= 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        print(f"Profit Factor    : {pf:.2f}")

    # Ledger Integrity Check
    ledger_pnl = sum(t["pnl"] for t in closed_trades)
    # Entry fees are deducted from balance but NOT included in trade PnL
    # So we need to account for them separately
    entry_trades = [t for t in trades if t.get("pnl") is None]
    total_entry_fees = sum(t.get("fee", 0) for t in entry_trades)
    adjusted_pnl = ledger_pnl - total_entry_fees
    delta = abs(total_pnl - adjusted_pnl)
    integrity = "✅ PASS" if delta < 0.01 else f"❌ FAIL (Δ=${delta:.4f})"
    print(f"Ledger Integrity : {integrity}")
    print(f"  Balance Δ      : ${total_pnl:+.4f}")
    print(f"  Trades Σ(PnL)  : ${ledger_pnl:+.4f}")
    print(f"  Entry Fees     : ${total_entry_fees:+.4f}")
    print("=" * 60 + "\n")
    sys.stdout.flush()
    sys.stderr.flush()

    await croupier.stop()
    sensor_mgr.stop()  # Phase 1201: Terminate worker processes AFTER croupier (prevents zombie processes)
    historian.stop()

    await connector.close()
    return


if __name__ == "__main__":
    try:
        asyncio.run(run_backtest())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"💥 Backtest failed: {e}", exc_info=True)
    finally:
        # Phase 2000: Force-exit to kill any zombie multiprocessing feeder threads.
        # multiprocessing.Queue uses background threads that can deadlock on pipe writes
        # if workers are terminated with unread data. os._exit bypasses all cleanup.
        os._exit(0)
