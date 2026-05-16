"""
3-Profile Comparative Backtest Runner
Runs EXPRIMIDOR, FRANCOTIRADOR, ESCALADOR sequentially on the same dataset
and produces a comparative summary.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Phase 1850: Simulation Time Interceptor
SIM_TIME = 0.0
_original_time = time.time


def sim_time_provider():
    return SIM_TIME if SIM_TIME > 0 else _original_time()


time.time = sim_time_provider

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config.trading as trading_config
from core.backtest_feed import BacktestFeed
from core.candle_maker import CandleMaker
from core.clock import Clock
from core.context_registry import ContextRegistry
from core.engine import Engine
from core.events import AggregatedSignalEvent, EventType, TickEvent
from core.sensor_manager import SensorManager
from croupier.croupier import Croupier
from decision.setup_engine import SetupEngineV4
from exchanges.adapters import ExchangeAdapter
from exchanges.connectors.virtual_exchange import VirtualExchangeConnector
from players.adaptive import AdaptivePlayer


async def run_single_profile(
    profile_name: str, data_path: str, symbol: str, balance: float, bet_size: float, limit: int = None
):
    """Run a single backtest with the specified exit profile."""
    global SIM_TIME
    SIM_TIME = 0.0

    # Set the active profile
    trading_config.ACTIVE_EXIT_PROFILE = profile_name
    _active = trading_config._EXIT_PROFILES.get(profile_name, trading_config._EXIT_PROFILES["EXPRIMIDOR"])
    trading_config.EXIT_LAYER_CATASTROPHIC = _active["LAYER_5_CATASTROPHIC"]
    trading_config.EXIT_LAYER_THESIS_INVALIDATION = _active["LAYER_4_INVALIDATION"]
    trading_config.EXIT_LAYER_SCE = _active["LAYER_3_SCE"]
    trading_config.EXIT_LAYER_SHADOW_PROTECTION = _active["LAYER_2_SHADOW"]
    trading_config.EXIT_LAYER_SESSION_DRAIN = _active["LAYER_1_DRAIN"]

    # Initialize Components
    engine = Engine()
    clock = Clock(tick_size_seconds=1.0)

    connector = VirtualExchangeConnector(
        initial_balance=balance, fee_rate=0.00035, maker_fee_rate=0.0001, slippage_rate=0.0001
    )
    adapter = ExchangeAdapter(connector, symbol=symbol)

    feed = BacktestFeed(
        engine=engine,
        data_path=data_path,
        symbol=symbol,
        delay=0.0,
        exchange_connector=connector,
        limit=limit,
        depth_db_path=None,
    )

    croupier = Croupier(exchange_adapter=adapter, initial_balance=balance, engine=engine)
    await connector.connect()

    def on_balance_update(bal: float, timestamp: float = None):
        croupier.balance_manager.set_balance(bal, timestamp=timestamp)

    connector.set_balance_update_callback(on_balance_update)

    async def no_op_async(*args, **kwargs):
        pass

    croupier.drift_auditor.start = no_op_async
    croupier.drift_auditor.stop = no_op_async
    croupier.drift_auditor.tick = no_op_async
    croupier.reconciliation.reconcile_symbol = no_op_async
    croupier.reconciliation.reconcile_all = no_op_async
    croupier._sync_balance = no_op_async
    croupier._sync_funding_fees = no_op_async

    await croupier.start()

    context_registry = ContextRegistry()
    croupier.context_registry = context_registry
    sensor_mgr = SensorManager(engine)
    setup_engine = SetupEngineV4(engine, context_registry=context_registry, fast_track=False)
    player = AdaptivePlayer(engine, croupier, fixed_pct=bet_size, context_registry=context_registry, fast_track=False)

    CandleMaker(engine, is_backtest=True)
    om = OrderManager(engine, croupier, player, setup_engine.tracker)
    await om.start()

    async def on_tick_context(e):
        global SIM_TIME
        SIM_TIME = e.timestamp
        context_registry.on_tick(e.symbol, e.price, e.volume, e.side)

    async def on_candle_context(e):
        context_registry.on_candle(e.symbol, e.high, e.low)

    async def on_micro_batch(e):
        for event in e.events:
            context_registry.set_micro_state(event.symbol, event.cvd, event.skewness, event.z_score)

    engine.subscribe(EventType.TICK, on_tick_context)
    engine.subscribe(EventType.CANDLE, on_candle_context)
    engine.subscribe(EventType.MICROSTRUCTURE_BATCH, on_micro_batch)
    engine.subscribe(EventType.SIGNAL, setup_engine.on_signal)

    # Import historian fresh
    from core.observability.historian import historian

    clock.add_iterator(adapter)
    clock.add_iterator(croupier)

    asyncio.create_task(clock.start())
    await feed.run()
    engine.running = False
    await clock.stop()
    await asyncio.sleep(0.5)

    closed_count = await connector.force_close_all_positions()
    stats = await connector.fetch_balance()
    final_balance = stats[connector.base_currency]["free"]
    total_pnl = final_balance - balance

    trades = connector._trades
    closed_trades = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] <= 0]

    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0
    total_fees = sum(t.get("fee", 0) for t in closed_trades)
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0

    # MFE/MAE analysis from trades
    mfe_list = []
    mae_list = []
    for t in closed_trades:
        if t.get("mfe_pct"):
            mfe_list.append(t["mfe_pct"])
        if t.get("mae_pct"):
            mae_list.append(t["mae_pct"])

    # Exit reason breakdown
    exit_reasons = {}
    for t in closed_trades:
        reason = t.get("exit_reason", "UNKNOWN")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    result = {
        "profile": profile_name,
        "final_balance": final_balance,
        "pnl": total_pnl,
        "pnl_pct": (total_pnl / balance) * 100,
        "total_trades": len(closed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "total_fees": total_fees,
        "net_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": pf,
        "expectancy": total_pnl / len(closed_trades) if closed_trades else 0,
        "exit_reasons": exit_reasons,
        "force_closed": closed_count,
    }

    await croupier.stop()
    sensor_mgr.stop()
    historian.stop()
    await connector.close()

    return result


async def main():
    DATA_PATH = "/home/chesterbelle/Casino-V3/data/raw/SOLUSDT_trades_2024_08.csv"
    SYMBOL = "SOL/USDT:USDT"
    BALANCE = 10000.0
    BET_SIZE = 0.01
    LIMIT = 1_500_000  # ~24h of SOL data

    profiles = ["EXPRIMIDOR", "FRANCOTIRADOR", "ESCALADOR"]
    results = []

    for profile in profiles:
        print(f"\n{'='*70}")
        print(f"🎰 RUNNING PROFILE: {profile}")
        print(f"{'='*70}")
        sys.stdout.flush()

        result = await run_single_profile(profile, DATA_PATH, SYMBOL, BALANCE, BET_SIZE, LIMIT)
        results.append(result)

        print(f"\n✅ {profile} Complete:")
        print(f"   PnL: ${result['pnl']:+.2f} ({result['pnl_pct']:+.2f}%)")
        print(f"   Trades: {result['total_trades']} | WR: {result['win_rate']:.1f}%")
        print(f"   PF: {result['profit_factor']:.2f}")
        print(f"   Fees: ${result['total_fees']:.2f}")
        print(f"   Exit Reasons: {result['exit_reasons']}")
        sys.stdout.flush()

    # Comparative Summary
    print(f"\n\n{'='*70}")
    print("📊 COMPARATIVE SUMMARY — ALL 3 PROFILES")
    print(f"{'='*70}")
    print(f"{'Metric':<25} {'EXPRIMIDOR':>15} {'FRANCOTIRADOR':>15} {'ESCALADOR':>15}")
    print("-" * 70)

    metrics = [
        ("PnL ($)", "pnl", "${:+.2f}"),
        ("PnL (%)", "pnl_pct", "{:+.2f}%"),
        ("Total Trades", "total_trades", "{}"),
        ("Win Rate", "win_rate", "{:.1f}%"),
        ("Profit Factor", "profit_factor", "{:.2f}"),
        ("Gross Profit", "gross_profit", "${:.2f}"),
        ("Gross Loss", "gross_loss", "${:.2f}"),
        ("Total Fees", "total_fees", "${:.2f}"),
        ("Avg Win", "avg_win", "${:.4f}"),
        ("Avg Loss", "avg_loss", "${:.4f}"),
        ("Expectancy/Trade", "expectancy", "${:.4f}"),
        ("Force-Closed", "force_closed", "{}"),
    ]

    for label, key, fmt in metrics:
        vals = []
        for r in results:
            vals.append(fmt.format(r[key]))
        print(f"{label:<25} {vals[0]:>15} {vals[1]:>15} {vals[2]:>15}")

    print(f"\n{'='*70}")
    print("📋 EXIT REASON BREAKDOWN")
    print(f"{'='*70}")
    all_reasons = set()
    for r in results:
        all_reasons.update(r["exit_reasons"].keys())

    print(f"{'Reason':<30} {'EXPRIMIDOR':>12} {'FRANCOTIRADOR':>12} {'ESCALADOR':>12}")
    print("-" * 70)
    for reason in sorted(all_reasons):
        vals = [str(r["exit_reasons"].get(reason, 0)) for r in results]
        print(f"{reason:<30} {vals[0]:>12} {vals[1]:>12} {vals[2]:>12}")

    print(f"\n{'='*70}")
    sys.stdout.flush()


if __name__ == "__main__":
    # Set logging to WARNING to speed up backtest
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )
    # But allow critical errors through
    logging.getLogger("Backtest-V4").setLevel(logging.WARNING)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"💥 Failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
    finally:
        os._exit(0)
