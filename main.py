"""
Casino V3 - Main Entry Point
Event-Driven Architecture with Fixed Bet Sizing

CLI Flags Reference:
| Flag | Default | Description |
|------|---------|-------------|
| `--exchange` | `binance` | Exchange driver (binance, hyperliquid) |
| `--symbol` | `BTC/USDT:USDT` | Trading Pair |
| `--mode` | `testing` | Execution Mode (live, testing, demo) |
| `--bet-size` | `0.01` | Position size (fraction of equity) |
| `--timeout` | `None` | Stop bot after N minutes |
| `--close-on-exit`| `False` | Force close all positions on shutdown (Ctrl+C) |
| `--wallet` | `None` | Wallet address (Override ENV) |
| `--key` | `None` | Private Key (Override ENV) |
"""

import argparse
import asyncio
import faulthandler
import logging
import os
import signal
import sys
import threading
import time

# Try uvloop for performance
try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass


from config import exchange as exchange_config
from config import trading as trading_config
from core.candle_maker import CandleMaker
from core.engine import Engine
from core.error_handling.error_handler import RetryConfig, get_error_handler
from core.events import EventType
from core.execution import OrderManager
from core.feed import StreamManager

# Setup observability
from core.observability import (
    configure_logging,
    start_metrics_server,
    stop_metrics_server,
    update_balance,
)
from core.observability.loop_monitor import LoopMonitor
from core.observability.metrics import bot_info
from core.observability.watchdog import watchdog
from core.sensor_manager import SensorManager
from croupier.croupier import Croupier
from decision.aggregator import SignalAggregatorV3
from exchanges.adapters import ExchangeAdapter
from exchanges.connectors import (
    BinanceNativeConnector,
    HyperliquidNativeConnector,
    ResilientConnector,
)

# Enable faulthandler to dump traceback on segfault/hard crash
faulthandler.enable()

# Configure structured logging (Clean Console by default, Detailed bot.log always)
configure_logging(log_level="INFO", log_format="console")
logger = logging.getLogger("Casino-V3")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Casino V3 Trading Bot")

    parser.add_argument(
        "--exchange",
        type=str,
        default="binance",
        choices=["binance", "hyperliquid"],
        help="Exchange to trade on (default: binance)",
    )

    parser.add_argument("--symbol", type=str, default="BTC/USDT:USDT", help="Trading symbol (default: BTC/USDT:USDT)")

    parser.add_argument(
        "--mode",
        type=str,
        default="testing",
        choices=["live", "testing", "demo"],
        help="Execution mode (default: testing)",
    )

    parser.add_argument(
        "--bet-size",
        type=float,
        default=0.01,
        help="Fixed bet size as fraction of equity (default: 0.01 = 1%%)",
    )

    parser.add_argument(
        "--close-on-exit",
        action="store_true",
        help="Close all open positions on shutdown (default: False)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Stop execution after N minutes (default: Run indefinitely)",
    )

    # Removed --max-positions: Player applies its own logic (default 1 per symbol)

    parser.add_argument("--wallet", type=str, help="Wallet address (overrides env)")
    parser.add_argument("--key", type=str, help="Private key (overrides env)")
    parser.add_argument("--max-symbols", type=int, help="Limit number of symbols for MULTI mode (Test)")

    return parser.parse_args()


async def main():
    """Main entry point for Casino V3."""
    args = parse_args()

    # Initialize centralized error handler
    error_handler = get_error_handler()

    # Retry configs
    startup_retry = RetryConfig(max_retries=5, backoff_base=2.0, backoff_max=30.0)
    network_retry = RetryConfig(max_retries=3, backoff_base=1.0)  # For lighter calls

    # Register signal handlers for graceful shutdown (SIGTERM for docker/pkill)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    startup_state = {"complete": False}  # Mutable container to avoid nonlocal

    def signal_handler():
        logger.info("🛑 Received shutdown signal")
        stop_event.set()
        if not startup_state["complete"]:
            # During startup, just mark for shutdown but don't cancel tasks yet
            logger.warning("⚠️ Shutdown deferred until startup completes...")
            return
        # Full cancellation only after startup
        for task in asyncio.all_tasks(loop):
            task.cancel()

    try:
        loop.add_signal_handler(signal.SIGTERM, signal_handler)
        loop.add_signal_handler(signal.SIGINT, signal_handler)
    except NotImplementedError:
        # Signal handling handles not supported on Windows
        pass

    logger.info(f"🚀 Starting Casino-V3 | Exchange: {args.exchange} | Mode: {args.mode}")

    # 0. Start Metrics Server
    logger.info("📊 Starting metrics server...")
    try:
        await error_handler.execute(
            start_metrics_server, port=8000, retry_config=startup_retry, context="metrics_server"
        )
        # Set bot info
        bot_info.info(
            {
                "version": "3.0.0",
                "exchange": args.exchange,
                "mode": args.mode,
                "symbol": args.symbol,
            }
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to start metrics server: {e}")

    # 0.1 Start Loop Lag Monitor
    loop_monitor = LoopMonitor(warning_threshold=0.1)
    loop_monitor.start()

    # 1. Initialize Exchange Adapter
    connector = None

    if args.exchange == "binance":
        # Binance Native Connector
        native = BinanceNativeConnector(
            api_key=args.wallet or exchange_config.BINANCE_API_KEY,
            secret=args.key or exchange_config.BINANCE_API_SECRET,
            mode="demo" if args.mode != "live" else "live",
        )

        # Wrap with Resilience (Circuit Breaker, Tracking, State Recovery)
        connector = ResilientConnector(
            connector=native,
            connection_config={
                "ws_backoff_base": 2.0,
                "ws_backoff_max": 60.0,
                "clock_enabled": False,  # Binance connector handles its own oco monitor or not needed if oco_manager uses callbacks
            },
            state_recovery_config={
                "state_dir": "./state",
                "auto_save_interval": 30.0,
            },
        )
    elif args.exchange == "hyperliquid":
        # Hyperliquid Native Connector

        connector = HyperliquidNativeConnector(
            api_key=args.key or os.getenv("HYPERLIQUID_API_SECRET"),  # Agent Private Key
            account_address=args.wallet or os.getenv("HYPERLIQUID_MAIN_WALLET"),  # Main Account Address
            mode="demo" if args.mode != "live" else "live",
            enable_websocket=True,
        )
    # Initialize Adapter
    adapter = ExchangeAdapter(connector, symbol=args.symbol)

    # 2. Initialize Core Engine
    engine = Engine()

    # 3. Initialize Croupier (Execution Layer)
    # 3. Initialize Croupier (Execution Layer)
    # Fetch actual balance from exchange
    # Use ErrorHandler to ensure connection succeeds
    await error_handler.execute(connector.connect, retry_config=startup_retry, context="exchange_connect")

    initial_balance_data = await error_handler.execute(
        connector.fetch_balance, retry_config=startup_retry, context="fetch_initial_balance"
    )
    initial_balance = initial_balance_data.get("total", {}).get("USDT", 10000.0)
    logger.info(f"💰 Initial Balance: {initial_balance:.2f} USDT")

    croupier = Croupier(exchange_adapter=adapter, initial_balance=initial_balance)

    # 3.1 Subscribe Exit Manager to events
    # 3.1 Subscribe Exit Manager to events
    engine.subscribe(EventType.AGGREGATED_SIGNAL, croupier.exit_manager.on_signal)
    engine.subscribe(EventType.CANDLE, croupier.exit_manager.on_candle)

    # 4. Initialize Data Feed
    data_feed = StreamManager(adapter, engine)
    engine.data_feed = data_feed  # Important for sensors

    # 5. Initialize Candle Maker (Tick → Candle)
    # Fixed 1m (60s) heartbeat for multi-timeframe aggregator compatibility
    CandleMaker(engine, timeframe_seconds=60)

    # 6. Initialize Sensor Manager (Candle → Signal)
    sensor_manager = SensorManager(engine)

    # 7. Initialize Signal Aggregator (Signal → Aggregated Signal)
    aggregator = SignalAggregatorV3(engine)
    tracker = aggregator.tracker  # Get tracker from aggregator

    # 8. Initialize Player (Aggregated Signal → Decision)
    from players.adaptive import AdaptivePlayer

    logger.info(f"🎰 Using Adaptive Player (bet_size={args.bet_size:.2%})")
    # Initialize Player (bet sizing) - max_positions defaults to 1 per symbol in Player
    player = AdaptivePlayer(engine, croupier, fixed_pct=args.bet_size)

    # 9. Initialize Order Manager (Decision → Execution)
    order_manager = OrderManager(engine, croupier, player, tracker)

    # 10. Initialize State Manager (for crash recovery)
    from core.state import StateManager

    state_manager = StateManager(
        position_tracker=croupier.position_tracker,
        balance_manager=croupier.balance_manager,
        state_dir="./state",
        save_interval=5,
    )

    # Define callback for immediate state persistence (Event-Driven)
    async def save_state_callback():
        try:
            await state_manager.sync_to_persistent()
        except Exception as e:
            logger.error(f"❌ Error in state save callback: {e}", exc_info=True)

    # Register callback with PositionTracker (fires on Open, Close, Audit)
    croupier.position_tracker.set_state_change_callback(save_state_callback)

    # --- Stats Collection ---
    closed_trades = []

    def on_trade_close(trade_id, result):
        """Callback to collect closed trade results."""
        closed_trades.append(result)
        # Note: persistence is now handled by state_change_callback

    # Hook callback into PositionTracker
    croupier.position_tracker.on_close_callback = on_trade_close

    # Register order update callback for OCO cancellation in live/demo mode
    # The callback is async, so we wrap it for the synchronous connector callback
    async def async_order_update_handler(order):
        # 1. Update Position Tracker (Current Limit/Stop management)
        await croupier.position_tracker.handle_order_update(order)
        # 2. Update OCO Manager (Initial entry wait)
        await croupier.oco_manager.on_order_update(order)

    connector.set_order_update_callback(async_order_update_handler)
    logger.info("✅ Order update callback registered for OCO cancellation")

    # Attempt recovery from previous session
    logger.info("🔄 Attempting state recovery...")
    recovered = await state_manager.recover()

    if recovered:
        logger.info("✅ State recovered from previous session")
        # Reconciliation will happen in the subscription loop for MULTI
    else:
        logger.info("📝 Starting fresh session")
        await state_manager.start(initial_balance)

    # 11. Multi-Asset Flytest & Startup
    # =========================================================
    active_symbols = []

    if args.symbol.upper() == "MULTI":
        # Allow MULTI in testing for architectural stability verification
        # if args.mode == "testing":
        #     logger.error("❌ Multi-Asset mode is NOT supported in Testing/Backtest mode yet. Please use single symbol.")
        #     sys.exit(1)

        from core.multi_asset_manager import MultiAssetManager

        multi_manager = MultiAssetManager(adapter)

        # Get target list (could be from config)
        targets = multi_manager.get_multi_config()

        # Run Flytest (now returns tuple with precision profile)
        # Use actual bet_size to calculate if trades meet min notional
        active_symbols, precision_profile = await error_handler.execute(
            multi_manager.run_flytest,
            target_symbols=targets,
            total_balance=initial_balance,
            bet_size=args.bet_size,
            sizing_mode=getattr(trading_config, "POSITION_SIZING_MODE", "FIXED_NOTIONAL"),
            stop_loss=getattr(trading_config, "STOP_LOSS", 0.01),
            retry_config=startup_retry,
            context="flytest",
        )

        if not active_symbols:
            logger.error("❌ No symbols passed Flytest! Shutting down.")
            return

        # RONDA 4/5: Limit symbols if requested
        if args.max_symbols:
            active_symbols = active_symbols[: args.max_symbols]
            logger.info(f"📉 Limited to Top {args.max_symbols} Symbols for Verification: {len(active_symbols)} symbols")

        logger.info(f"🚀 Starting MULTI mode with: {active_symbols}")
        logger.info(f"📐 Precision Profile loaded: {len(precision_profile)} symbols")

        # --- LIQUIDITY WATCHDOG (Flytest 3.0) ---
        async def on_liquidity_fail_callback(symbol):
            logger.warning(f"🚫 Watchdog Callback: Unsubscribing from {symbol}")
            await data_feed.unsubscribe_all(symbol)

        # Start the watchdog task (Fire and Forget but keep ref)
        asyncio.create_task(
            multi_manager.start_liquidity_watchdog(
                active_list=active_symbols,
                on_remove_callback=on_liquidity_fail_callback,
                interval=300,  # 5 minutes
                bet_size_pct=args.bet_size,
            )
        )
        logger.info("🐶 Liquidity Watchdog background task launched.")
        # ----------------------------------------
    else:
        # Single mode
        active_symbols = [args.symbol]

    # STARTUP RECONCILIATION: Adopt unknown positions instead of sweeping them
    # CRITICAL: First discover ALL symbols with activity on the exchange (orphan detection)
    # This catches orphans from previous sessions that are NOT in Flytest list
    logger.info("🔍 Discovering exchange orphans before reconciliation...")
    try:
        exchange_orphan_symbols = await adapter.fetch_active_symbols()
        if exchange_orphan_symbols:
            # Merge with active_symbols (avoiding duplicates)
            combined_symbols = list(set(active_symbols + exchange_orphan_symbols))
            if len(combined_symbols) > len(active_symbols):
                new_orphans = set(exchange_orphan_symbols) - set(active_symbols)
                logger.warning(f"⚠️ Found {len(new_orphans)} orphan symbols not in Flytest: {new_orphans}")
            active_symbols = combined_symbols
    except Exception as e:
        logger.error(f"❌ Failed to discover orphans: {e}")

    # OPTIMIZED: Batch reconciliation for all active symbols
    logger.info("🧹 Performing startup reconciliation (Batch Sync)...")

    sweep_report = {"positions_closed": 0, "orders_cancelled": 0, "ghosts_removed": 0, "positions_fixed": 0}

    try:
        # Use reconcile_all (returns a list of reports)
        reconcile_results = await croupier.reconcile_positions()

        # Aggregate results
        for report in reconcile_results:
            sweep_report["positions_closed"] += report.get("positions_closed", 0)
            sweep_report["orders_cancelled"] += report.get("orders_cancelled", 0)
            sweep_report["ghosts_removed"] += report.get("ghosts_removed", 0)
            sweep_report["positions_fixed"] += report.get("positions_fixed", 0)
    except Exception as e:
        logger.error(f"❌ Startup reconciliation failed: {e}")

    if (
        sweep_report["positions_closed"] > 0
        or sweep_report["orders_cancelled"] > 0
        or sweep_report["positions_fixed"] > 0
    ):
        logger.info(
            f"📊 Startup Report: "
            f"Adopted={sweep_report['positions_fixed']}, "
            f"Fixed={sweep_report['ghosts_removed']}, "
            f"Closed={sweep_report['positions_closed']}, "
            f"Cancelled={sweep_report['orders_cancelled']}"
        )
    else:
        logger.info("✅ Exchange is clean/synced (no changes needed)")

    # Mark startup as complete - now signals can cancel tasks normally
    startup_state["complete"] = True
    logger.info("🚀 Startup complete - Signal handling enabled")

    # Check if shutdown was requested during startup
    if stop_event.is_set():
        logger.warning("⚠️ Shutdown was requested during startup. Exiting gracefully...")
        return

    # Start components (connector already connected for balance fetch)
    # await connector.connect()  # Already connected above

    # Store initial balance for PnL calc
    # CRITICAL FIX (Phase 30): ALWAYS prioritize the fresh wallet balance fetched at startup
    # over any recovered value from persistent state to avoid "stale balance" paradox.
    fresh_balance = float(croupier.balance_manager.get_balance())

    state = state_manager.persistent_state.get_state()
    if state and state.initial_balance > 0:
        if abs(state.initial_balance - fresh_balance) > 1.0:  # Significant difference
            logger.warning(
                f"⚠️ Recovered balance ({state.initial_balance}) differs from Wallet ({fresh_balance}). Prioritizing Wallet."
            )

    initial_balance = fresh_balance
    logger.info(f"💰 Session Initial Balance: {initial_balance:.2f} USDT (GROUND TRUTH)")

    # Sync Croupier with the definitive start balance
    croupier.set_process_start_balance(initial_balance)

    # Update initial balance metrics
    update_balance(
        exchange=args.exchange,
        total=initial_balance,
        available=initial_balance,
        allocated=0.0,
    )

    await order_manager.start()
    await engine.start(blocking=False)

    # Start Watchdog Monitor Loop
    await watchdog.start()
    watchdog.register("main_loop", timeout=30.0)

    # --- Persistence & Recovery ---
    # --- Periodic Reconciliation Loop ---
    # Crucial for recovering from network outages where "Close" events were missed.
    async def reconciliation_loop():
        """Periodically force reconciliation to clear ghosts/orphans."""
        logger.info("🔄 Periodic reconciliation loop started (Interval: 300s)")
        watchdog.register("reconciliation_loop", timeout=600.0)  # 10 min timeout
        while True:
            # Report heartbeat before sleep
            watchdog.heartbeat("reconciliation_loop", "Waiting for next cycle")
            await asyncio.sleep(300)  # Run every 5 minutes
            try:
                logger.info("🔄 Running global periodic reconciliation...")
                reports = await error_handler.execute(
                    croupier.reconcile_positions, retry_config=network_retry, context="global_reconcile"
                )

                # Report heartbeat after successful (or attempted) execution
                watchdog.heartbeat("reconciliation_loop", "Finished global reconciliation")

                for report in reports:
                    if (
                        report.get("ghosts_removed", 0) > 0
                        or report.get("positions_fixed", 0) > 0
                        or report.get("positions_closed", 0) > 0
                    ):
                        sym = report.get("symbol", "UNKNOWN")
                        logger.warning(
                            f"⚠️ Reconciliation fixed {sym}: Ghosts={report.get('ghosts_removed', 0)}, "
                            f"Adopted={report.get('positions_fixed', 0)}, Closed={report.get('positions_closed', 0)}"
                        )
            except Exception as e:
                logger.error(f"❌ Periodic reconciliation failed: {e}")

    reconciliation_task = asyncio.create_task(reconciliation_loop())

    # Subscribe to ticker & trades for ALL active symbols
    for sym in active_symbols:
        logger.info(f"📡 Subscribing to {sym}...")
        await data_feed.subscribe_ticker(sym)
        await data_feed.subscribe_trades(sym)
        # Spread the initial task creation load
        await asyncio.sleep(0.5)

    logger.info("✅ Casino-V3 Running | Press Ctrl+C to stop")
    if args.timeout:
        logger.info(f"⏰ Timer set: Stopping in {args.timeout} minutes.")

    # Mark startup as complete
    startup_state["complete"] = True
    logger.info("🏁 Startup complete - entering main loop")

    start_time = time.time()
    exit_reason_str = "SHUTDOWN"

    try:
        while engine.running and not stop_event.is_set():
            # Report main loop heartbeat
            watchdog.heartbeat("main_loop", "Active / Engine running")
            await asyncio.sleep(1)

            # Check timeout
            if args.timeout:
                elapsed_min = (time.time() - start_time) / 60

                # A. Drain Phase (Soft Timeout)
                if elapsed_min >= (args.timeout - trading_config.DRAIN_PHASE_MINUTES):
                    if not croupier.is_drain_mode:
                        logger.warning(
                            f"🕒 Entering DRAIN PHASE ({trading_config.DRAIN_PHASE_MINUTES}m remaining). "
                            "Stopping new entries and narrowing TPs..."
                        )
                        croupier.set_drain_mode(True)

                    # Progressive Exit Update
                    remaining = args.timeout - elapsed_min
                    # Fire and forget (it handles its own async logic or internal checks)
                    # We use create_task to avoid blocking the main loop with exit logic
                    asyncio.create_task(croupier.update_drain_status(remaining))

                # B. Hard Timeout (Session Ends)
                if elapsed_min >= args.timeout:
                    logger.info(f"⏰ Timeout reached ({args.timeout}m). Stopping session.")
                    exit_reason_str = "TIMEOUT"
                    break

        # Why did the loop exit?
        if not engine.running:
            logger.error("🚨 Loop exited: Engine.running is False!")
            exit_reason_str = "ENGINE_LOST" if exit_reason_str == "SHUTDOWN" else exit_reason_str
        elif stop_event.is_set():
            logger.warning("🚨 Loop exited: stop_event is set!")
            exit_reason_str = "SIGNAL_STOP" if exit_reason_str == "SHUTDOWN" else exit_reason_str

    except asyncio.CancelledError:
        logger.info("🛑 Main task cancelled")
        exit_reason_str = "CANCELLED"
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down (KeyboardInterrupt)...")
        exit_reason_str = "MANUAL_STOP"
    except Exception as e:
        logger.critical(f"💥 FATAL CRASH in main loop: {e}", exc_info=True)
        exit_reason_str = "CRASH"
    finally:
        logger.info("🧹 Cleaning up resources...")

        # --- HEARTBEAT WATCHDOG ---
        class HeartbeatWatchdog:
            def __init__(self, timeout: float = 60.0):
                self.timeout = timeout
                self.last_heartbeat = time.time()
                self.stop_event = threading.Event()
                self._thread = None

            def heartbeat(self):
                self.last_heartbeat = time.time()
                logger.debug("💓 Watchdog Heartbeat received")

            def start(self):
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
                logger.info(f"🐶 Heartbeat Watchdog started (Initial timeout: {self.timeout}s)")

            def stop(self):
                self.stop_event.set()
                if self._thread:
                    self._thread.join(timeout=1.0)

            def _run(self):
                while not self.stop_event.is_set():
                    elapsed = time.time() - self.last_heartbeat
                    if elapsed > self.timeout:
                        logger.critical(f"🚨 Cleanup HANG detected! (No progress for {elapsed:.1f}s). Force killing.")
                        sys.stdout.flush()
                        sys.stderr.flush()
                        # Use os._exit for immediate hard kill
                        import os

                        os._exit(1)
                    time.sleep(1.0)

        # 0. Watchdog for Cleanup (Protection against hangs)
        # Rename local to avoiding shadowing the global watchdog registry
        cleanup_watchdog = HeartbeatWatchdog(timeout=120.0)
        cleanup_watchdog.start()
        cleanup_watchdog.heartbeat()  # Entry heartbeat

        # 0. Cancel background tasks created in main()

        # 0.5. STOP INPUTS AND PROCESSING (PRIORITY)
        # We stop sensors and engine FIRST so the loop is quiet during sweep
        try:
            logger.info("🛑 Stopping background tasks and managers...")

            # Stop Sensors (multiprocessing)
            sensor_manager.stop()

            # Stop Engine & OrderManager (Accept no more events)
            await asyncio.wait_for(engine.stop(), timeout=5.0)
            await asyncio.wait_for(order_manager.stop(), timeout=5.0)

            # Cancel specific background tasks
            health_check_task = locals().get("health_check_task")
            if health_check_task:
                health_check_task.cancel()
            reconciliation_task = locals().get("reconciliation_task")
            if reconciliation_task:
                reconciliation_task.cancel()

        except Exception as e:
            logger.error(f"⚠️ Error during early shutdown: {e}")

        # 0.6. Emergency Sweep / Close Positions (PRIORITY)
        logger.info("🧹 Performing final exchange sweep...")
        should_close = args.close_on_exit

        try:
            # We use an unconstrained wait for this critical operation (Smart Exit)
            logger.info(
                f"🧹 Emergency Sweep: {'Closing Positions' if should_close else 'Cancelling Orders'} (Reason: {exit_reason_str})"
            )
            # Pass watchdog for heartbeat signaling
            sweep_task = croupier.emergency_sweep(
                symbols=[args.symbol] if args.symbol and args.symbol != "MULTI" else None,
                close_positions=should_close,
                reason=exit_reason_str,
                watchdog=cleanup_watchdog,  # Pass the watchdog to signal progress
            )
            await sweep_task
        except Exception as e:
            logger.error(f"❌ Error during emergency sweep: {e}")
        finally:
            cleanup_watchdog.heartbeat()  # Final heartbeat after sweep

        # 0.75. Fetch REAL final balance from exchange (PRIORITY for summary)
        final_balance_usdt = "N/A"
        try:
            logger.info("💰 Fetching final balance from exchange...")
            bal = await asyncio.wait_for(croupier.adapter.fetch_balance(), timeout=10.0)
            final_balance_usdt = bal.get("total", {}).get("USDT", "N/A")
            # Update state with final balance
            state = state_manager.persistent_state.get_state()
            if state:
                state.current_balance = (
                    float(final_balance_usdt) if final_balance_usdt != "N/A" else state.current_balance
                )
        except Exception as e:
            logger.error(f"❌ Error fetching final balance: {e}")

        # 0.77. NOW disconnect connector (after all exchange operations complete)
        try:
            logger.info("🔌 Disconnecting exchange connector...")
            await croupier.adapter.disconnect()
        except Exception as e:
            logger.error(f"⚠️ Error disconnecting connector: {e}")

        # 0.8. Generate Session Report (PRIORITY - Precise Historian Data)
        logger.info("📊 Generating Session Report...")
        try:
            # Pass final wallet balance to calculate leakage/adjustment
            summary = croupier.get_session_summary(final_balance=final_balance_usdt)

            total_trades = summary.get("count", 0)
            wins = summary.get("wins", 0)
            losses = summary.get("losses", 0)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

            strategy_net_pnl = summary.get("total_net_pnl", 0.0)
            adjustment = summary.get("leakage", 0.0)
            account_delta = summary.get("account_delta", 0.0)
            total_fees = summary.get("total_fees", 0.0)

            start_bal = summary.get("start_balance", 0.0)

            logger.info("==========================================")
            logger.info("🏁 SESSION SUMMARY (Persistent Historian)")
            logger.info(f"   Reason: {exit_reason_str}")
            logger.info(f"   Start Balance: {start_bal:.2f} USDT")
            logger.info(f"   Final Balance: {final_balance_usdt} USDT")
            logger.info("   --------------------------------------")
            logger.info(f"   📈 Strategy PnL: {strategy_net_pnl:+.4f} USDT")
            logger.info(f"   🧹 Audit Adjust: {adjustment:+.4f} USDT (Ghosts/Fees/Funding)")
            logger.info(f"   💰 Account Delta: {account_delta:+.4f} USDT (ACTUAL)")
            logger.info("   --------------------------------------")
            logger.info(f"   Total Fees Paid: {total_fees:.4f} USDT")
            logger.info(f"   Total Trades: {total_trades}")
            logger.info(f"   Wins/Losses: {wins}/{losses} (WR: {win_rate:.2f}%)")
            logger.info("==========================================")
        except Exception as e:
            logger.error(f"❌ Error generating summary: {e}")

        # 1. STOP REMAINING COMPONENTS
        # (Engine and OrderManager stopped earlier)
        # (SensorManager stopped earlier)

        # 2. Sync final state before closing positions
        logger.info("💾 Syncing final state...")
        try:
            await asyncio.wait_for(state_manager.sync_to_persistent(), timeout=5.0)
        except Exception as e:
            logger.error(f"❌ Error syncing final state: {e}")

        # 3. Stop state manager (final save)
        logger.info("🛑 Stopping state manager...")
        try:
            await asyncio.wait_for(state_manager.stop(), timeout=2.0)
        except Exception as e:
            logger.error(f"❌ Error stopping state manager: {e}")

        # 4. Stop metrics server
        logger.info("📊 Stopping metrics server...")
        try:
            await asyncio.wait_for(stop_metrics_server(), timeout=2.0)
        except Exception as e:
            logger.error(f"❌ Error stopping metrics server: {e}")

        # 5. Stop Watchdog
        await watchdog.stop()

        logger.info("🏁 Cleanup complete. Goodbye.")
        os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())
