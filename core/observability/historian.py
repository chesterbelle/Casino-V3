import asyncio
import logging
import multiprocessing as mp
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradeHistorian")


def _historian_worker(db_path: str, q: mp.Queue):
    """Background Multi-Process Worker for DB I/O (Phase 240)."""
    import logging
    import sqlite3
    from datetime import datetime

    worker_logger = logging.getLogger("HistorianWorker")
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception as e:
        worker_logger.error(f"HistorianWorker failed to connect to DB: {e}")
        return

    while True:
        try:
            item = q.get()
            if item is None:
                break

            action, data = item
            if action == "INSERT_TRADE":
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trades
                    (trade_id, symbol, side, entry_price, exit_price, qty, fee, funding, gross_pnl, net_pnl, exit_reason, timestamp, bars_held, session_id, healed, t0_signal_ts, t1_decision_ts, t2_submit_ts, t4_fill_ts, slippage_pct, lifecycle_phase, setup_type, level_ref, level_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    data,
                )
                conn.commit()
            elif action == "INSERT_DEPTH":
                conn.execute(
                    """
                    INSERT INTO depth_snapshots (timestamp, symbol, bids, asks)
                    VALUES (?, ?, ?, ?)
                    """,
                    data,
                )
                conn.commit()
            elif action == "INSERT_SIGNAL":
                conn.execute(
                    """
                    INSERT INTO signals (timestamp, symbol, side, setup_type, price, metadata, session_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    data,
                )
                conn.commit()
            elif action == "INSERT_PRICE_SAMPLE":
                conn.execute(
                    """
                    INSERT INTO price_samples (timestamp, symbol, price)
                    VALUES (?, ?, ?)
                    """,
                    data,
                )
                conn.commit()
            elif action == "RECONCILE_LEDGER":
                income_records, session_id, min_timestamp = data
                for record in income_records:
                    income_type = record.get("incomeType")
                    if income_type not in ["FUNDING_FEE", "INSURANCE_CLEAR", "ADJUSTMENT", "COMMISSION"]:
                        continue

                    tran_id = str(record.get("tranId"))
                    cursor = conn.execute("SELECT 1 FROM trades WHERE trade_id = ?", (tran_id,))
                    if cursor.fetchone():
                        continue

                    ts_ms = record.get("time", 0)
                    record_ts = ts_ms / 1000.0

                    actual_session = session_id or "LEDGER_SYNC"
                    if min_timestamp and record_ts < min_timestamp:
                        actual_session = "LEGACY_AUDIT"

                    amount = float(record.get("income", 0.0))
                    symbol = record.get("symbol", "UNKNOWN")
                    timestamp = datetime.fromtimestamp(record_ts).isoformat()

                    gross = 0.0
                    fee = 0.0
                    funding = 0.0

                    if income_type == "FUNDING_FEE":
                        funding = -amount
                    elif income_type == "COMMISSION":
                        fee = -amount
                    else:
                        gross = amount

                    net_pnl = gross - fee - funding

                    conn.execute(
                        """
                        INSERT INTO trades
                        (trade_id, symbol, side, entry_price, exit_price, qty, fee, funding, gross_pnl, net_pnl, exit_reason, timestamp, bars_held, session_id, healed)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tran_id,
                            symbol,
                            "FLAT",
                            0.0,
                            0.0,
                            0.0,
                            fee,
                            funding,
                            gross,
                            net_pnl,
                            income_type,
                            timestamp,
                            0,
                            actual_session,
                            0,
                        ),
                    )
                conn.commit()
        except Exception as e:
            worker_logger.error(
                f"HistorianWorker error processing {action if 'action' in locals() else 'unknown'}: {e}"
            )

    conn.close()


class TradeHistorian:
    """
    Persistent trade historian using SQLite with non-blocking writes.
    Tracks every trade with precision accounting (Fees, Funding, Net PnL).
    """

    def __init__(self, db_path: str = "data/historian.db"):
        self.db_path = db_path
        self._conn = None
        self._use_mp = self.db_path != ":memory:"

        if self.db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._ensure_data_dir()
        self._init_db()

        # Phase 240: HFT Footprint Decoupling (Multiprocessing for I/O)
        self._queue = None
        self._worker_process = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="HistorianDB_Legacy")
        self._loop = None

        if self._use_mp:
            # We don't start the process here to avoid multiprocessing import locks.
            # It will be started lazily in _ensure_worker()
            pass

    def _ensure_data_dir(self):
        """Ensures the directory for the database exists."""
        if self.db_path == ":memory:":
            return
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _ensure_worker(self):
        """Lazily starts the background worker process."""
        if self._use_mp and self._worker_process is None:
            self._queue = mp.Queue()
            self._worker_process = mp.Process(
                target=_historian_worker, args=(self.db_path, self._queue), name="HistorianWorker", daemon=True
            )
            self._worker_process.start()
            logger.info("🚀 HistorianWorker Process started for ultra-low latency I/O.")

    def _init_db(self):
        """Initializes the database schema."""
        if self._conn:
            conn = self._conn
            self._apply_schema(conn)
        else:
            with sqlite3.connect(self.db_path) as conn:
                self._apply_schema(conn)

    def _apply_schema(self, conn):
        """Applies schema to a connection."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE,
                symbol TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                qty REAL,
                fee REAL DEFAULT 0.0,
                funding REAL DEFAULT 0.0,
                gross_pnl REAL,
                net_pnl REAL,
                exit_reason TEXT,
                timestamp TEXT,
                bars_held INTEGER,
                session_id TEXT,
                healed BOOLEAN DEFAULT 0,
                t4_fill_ts REAL,
                slippage_pct REAL,
                lifecycle_phase TEXT DEFAULT 'ACTIVE',
                setup_type TEXT DEFAULT 'unknown',
                level_ref TEXT DEFAULT 'unknown',
                level_price REAL DEFAULT 0.0
            )
        """
        )

        # Phase 1300: L2 Hybrid Simulation (Depth Snapshots)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS depth_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                symbol TEXT,
                bids TEXT,
                asks TEXT
            )
            """
        )
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_depth_ts_sym ON depth_snapshots(timestamp, symbol)")
        except sqlite3.OperationalError:
            pass
        # Schema Evolution: Add session_id if it doesn't exist
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN session_id TEXT")
        except sqlite3.OperationalError:
            pass  # Already exists

        # Phase 61: Schema Evolution for Resilience Attribution
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN healed BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Already exists

        # Phase 85: Schema Evolution for Latency Telemetry
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN t0_signal_ts REAL")
            conn.execute("ALTER TABLE trades ADD COLUMN t1_decision_ts REAL")
            conn.execute("ALTER TABLE trades ADD COLUMN t2_submit_ts REAL")
            conn.execute("ALTER TABLE trades ADD COLUMN t4_fill_ts REAL")
            conn.execute("ALTER TABLE trades ADD COLUMN slippage_pct REAL")
        except sqlite3.OperationalError:
            pass  # Already exists

        # Phase 650: Setup Type Attribution
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN setup_type TEXT DEFAULT 'unknown'")
        except sqlite3.OperationalError:
            pass  # Already exists

        # Phase 800: Setup Edge Auditor Tables
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                symbol TEXT,
                side TEXT,
                setup_type TEXT,
                price REAL,
                metadata TEXT,
                session_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                symbol TEXT,
                price REAL
            )
            """
        )
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_ts_sym ON price_samples(timestamp, symbol)")
        except sqlite3.OperationalError:
            pass

        conn.commit()

    @contextmanager
    def _get_conn(self):
        """Context manager for DB connection (handles :memory: persistence)."""
        if self._conn:
            yield self._conn
        else:
            with sqlite3.connect(self.db_path) as conn:
                yield conn

    def _get_loop(self):
        """Get or initialize the current event loop."""
        if not self._loop:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                # If no loop is running in this thread, we can't do much async
                return None
        return self._loop

    def _run_async(self, fn, *args):
        """Offloads a blocking function to the thread pool."""
        loop = self._get_loop()
        if loop and loop.is_running():
            return loop.run_in_executor(self._executor, fn, *args)
        else:
            # Fallback for sync contexts or startup/shutdown where loop is not ready
            return fn(*args)

    def stop(self):
        """Phase 240: Graceful shutdown. Flushes queues and stops workers."""
        if self._use_mp and self._worker_process:
            self._queue.put(None)
            self._worker_process.join(timeout=5.0)
            self._worker_process = None
            logger.info("🛑 HistorianWorker Process stopped.")

        if self._executor:
            self._executor.shutdown(wait=True)
            logger.info("🛑 Historian Legacy Executor stopped.")

    def record_depth_snapshot(self, timestamp: float, symbol: str, bids: str, asks: str):
        """
        Phase 1300: L2 Simulation. Dispatches depth snapshot to background worker.
        """
        if not self._use_mp:
            return  # Skip if memory DB

        self._ensure_worker()
        self._queue.put(("INSERT_DEPTH", (timestamp, symbol, bids, asks)))

    def record_signal(
        self, timestamp: float, symbol: str, side: str, setup_type: str, price: float, metadata: str, session_id: str
    ):
        """
        Phase 800: Edge Auditor. Records raw signals for post-trade Alpha analysis.
        """
        if not self._use_mp:
            return

        self._ensure_worker()
        self._queue.put(("INSERT_SIGNAL", (timestamp, symbol, side, setup_type, price, metadata, session_id)))

    def record_price_sample(self, timestamp: float, symbol: str, price: float):
        """
        Phase 800: Edge Auditor. Records high-frequency price snapshots for MFE/MAE analysis.
        """
        if not self._use_mp:
            return

        self._ensure_worker()
        self._queue.put(("INSERT_PRICE_SAMPLE", (timestamp, symbol, price)))

    def record_trade(self, trade_data: Dict[str, Any]):
        """
        Records a completed trade into the database. (Non-blocking pipeline)
        """
        try:
            trade_id = trade_data.get("trade_id")
            if not trade_id:
                logger.error("❌ Historian: Cannot record trade without trade_id")
                return
            trade_id = str(trade_id)  # Enforce TEXT mapping for SQLite

            entry_price = float(trade_data.get("entry_price", 0.0))
            exit_price = float(trade_data.get("exit_price", 0.0))

            if entry_price <= 0:
                logger.warning(f"⚠️ Historian: Trade {trade_id} has invalid entry_price: {entry_price}. Skipping.")
                return

            gross = float(trade_data.get("pnl", 0.0))
            fee = float(trade_data.get("fee", 0.0))
            funding = float(trade_data.get("funding", 0.0))
            net_pnl = gross - fee - funding

            qty = float(trade_data.get("qty", 0.0))
            if qty <= 0:
                notional = float(trade_data.get("notional", 0.0))
                qty = notional / entry_price if entry_price > 0 else 0.0

            if qty <= 0:
                logger.warning(
                    f"⚠️ Historian: Trade {trade_id} has 0 qty and 0 notional. Forcing minimum for traceability."
                )
                qty = 0.00000001

            session_id = trade_data.get("session_id")
            healed = 1 if trade_data.get("healed") else 0

            params = (
                trade_id,
                trade_data.get("symbol"),
                trade_data.get("side"),
                entry_price,
                exit_price,
                qty,
                fee,
                funding,
                gross,
                net_pnl,
                trade_data.get("exit_reason"),
                datetime.now().isoformat(),
                trade_data.get("bars_held", 0),
                session_id,
                healed,
                trade_data.get("t0_signal_ts"),
                trade_data.get("t1_decision_ts"),
                trade_data.get("t2_submit_ts"),
                trade_data.get("t4_fill_ts"),
                trade_data.get("slippage_pct"),
                trade_data.get("lifecycle_phase", "ACTIVE"),
                trade_data.get("setup_type", "unknown"),
                trade_data.get("level_ref", "unknown"),
                trade_data.get("level_price", 0.0),
            )

            if self._use_mp:
                self._ensure_worker()
                self._queue.put(("INSERT_TRADE", params))
                logger.info(f"💾 Historian: Queued trade {trade_id} ({trade_data.get('symbol')}) -> MP Worker")
            else:
                self._run_async(self._execute_insert_trade, params)
                logger.info(f"💾 Historian: Registered trade {trade_id} ({trade_data.get('symbol')}) | Sync")

        except Exception as e:
            logger.error(f"❌ Historian: Error processing trade record: {e}")

    def _execute_insert_trade(self, params):
        """Fallback sync executor for memory DBs."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trades
                    (trade_id, symbol, side, entry_price, exit_price, qty, fee, funding, gross_pnl, net_pnl, exit_reason, timestamp, bars_held, session_id, healed, t0_signal_ts, t1_decision_ts, t2_submit_ts, t4_fill_ts, slippage_pct, lifecycle_phase, setup_type, level_ref, level_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    params,
                )
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Historian: Error in sync execute: {e}")

    def reconcile_ledger(
        self,
        income_records: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        min_timestamp: Optional[float] = None,
    ):
        """
        Reconciles Ledger (Income History) to capture missing Funding Fees. (Non-blocking)
        """
        if self._use_mp:
            self._ensure_worker()
            self._queue.put(("RECONCILE_LEDGER", (income_records, session_id, min_timestamp)))
            logger.info(f"💾 Historian: Queued ledger reconciliation ({len(income_records)} records) -> MP Worker")
        else:
            return self._run_async(self._reconcile_ledger_sync, income_records, session_id, min_timestamp)

    def _reconcile_ledger_sync(
        self,
        income_records: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        min_timestamp: Optional[float] = None,
    ):
        """Internal synchronous reconciliation logic."""
        count = 0
        total_restored = 0.0

        with self._get_conn() as conn:
            for record in income_records:
                income_type = record.get("incomeType")
                # Only target safe types that are definitely not duplicate trade PnL
                if income_type not in ["FUNDING_FEE", "INSURANCE_CLEAR", "ADJUSTMENT", "COMMISSION"]:
                    continue

                tran_id = str(record.get("tranId"))

                # Check existence
                cursor = conn.execute("SELECT 1 FROM trades WHERE trade_id = ?", (tran_id,))
                if cursor.fetchone():
                    continue

                # Phase 110: Time-Fence Isolation
                ts_ms = record.get("time", 0)
                record_ts = ts_ms / 1000.0

                # Determine session attribution
                actual_session = session_id or "LEDGER_SYNC"
                if min_timestamp and record_ts < min_timestamp:
                    # Capture it for Truth, but exclude from active strategy reporting
                    actual_session = "LEGACY_AUDIT"

                # Prepare record
                amount = float(record.get("income", 0.0))
                symbol = record.get("symbol", "UNKNOWN")
                # Timestamp from ms to ISO
                timestamp = datetime.fromtimestamp(record_ts).isoformat()

                # Calculating columns
                gross = 0.0
                fee = 0.0
                funding = 0.0

                if income_type == "FUNDING_FEE":
                    funding = -amount
                elif income_type == "COMMISSION":
                    fee = -amount
                else:
                    gross = amount

                # Verify math
                net_pnl = gross - fee - funding

                conn.execute(
                    """
                    INSERT INTO trades
                    (trade_id, symbol, side, entry_price, exit_price, qty, fee, funding, gross_pnl, net_pnl, exit_reason, timestamp, bars_held, session_id, healed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tran_id,
                        symbol,
                        "FLAT",  # side
                        0.0,
                        0.0,
                        0.0,  # prices/qty
                        fee,
                        funding,
                        gross,
                        net_pnl,
                        income_type,  # exit_reason
                        timestamp,
                        0,  # bars_held
                        actual_session,
                        1,  # healed (it's a system fix)
                    ),
                )
                count += 1
                total_restored += amount

            conn.commit()

        if count > 0:
            logger.info(
                f"💰 Ledger Reconciliation: Restored {count} records | Total Impact: {total_restored:+.4f} USDT"
            )

    def update_trade_fee(self, trade_id: str, fee: float, exit_price: Optional[float] = None):
        """
        Updates the fee (and optionally exit_price) for an existing trade record. (Non-blocking)
        """
        return self._run_async(self._update_trade_fee_sync, trade_id, fee, exit_price)

    def _update_trade_fee_sync(self, trade_id: str, fee: float, exit_price: Optional[float] = None):
        """Internal synchronous update logic."""
        trade_id = str(trade_id)  # Enforce TEXT mapping for SQLite
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT gross_pnl, funding, entry_price, side, qty FROM trades WHERE trade_id = ?", (trade_id,)
                )
                row = cursor.fetchone()

                if not row:
                    logger.warning(f"⚠️ Historian: Cannot update fee for unknown trade_id {trade_id}")
                    return

                gross = float(row["gross_pnl"])
                funding = float(row["funding"])
                entry_price = float(row["entry_price"])
                side = row["side"]
                qty = float(row["qty"])

                # If exit_price is provided, recalculate gross_pnl
                new_gross = gross
                if exit_price is not None:
                    direction = 1 if side.upper() in ["LONG", "BUY"] else -1
                    new_gross = (exit_price - entry_price) * qty * direction

                new_net = new_gross - fee - funding

                if exit_price is not None:
                    conn.execute(
                        "UPDATE trades SET fee = ?, exit_price = ?, gross_pnl = ?, net_pnl = ? WHERE trade_id = ?",
                        (fee, exit_price, new_gross, new_net, trade_id),
                    )
                else:
                    conn.execute(
                        "UPDATE trades SET fee = ?, net_pnl = ? WHERE trade_id = ?",
                        (fee, new_net, trade_id),
                    )
                conn.commit()
            logger.info(f"✅ Historian: Enriched trade {trade_id} with fee {fee:.6f}")
        except Exception as e:
            logger.error(f"❌ Historian: Error updating fee for {trade_id}: {e}")

    def record_external_closure(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        exit_price: float,
        fee: float = 0.0,
        funding: float = 0.0,
        reason: str = "AUDIT_SWEEP",
        session_id: Optional[str] = None,
    ):
        """
        Records a closure that happened outside the normal OCO lifecycle (e.g. sweep).
        """
        try:
            # PnL = (Exit - Entry) * Qty * Direction
            direction = 1 if side.upper() in ["LONG", "BUY"] else -1
            gross_pnl = (exit_price - entry_price) * qty * direction
            net_pnl = gross_pnl - fee - funding

            trade_id = f"EXT_{reason}_{datetime.now().strftime('%H%M%S%f')[:8]}"

            trade_data = {
                "trade_id": trade_id,
                "symbol": symbol,
                "side": "LONG" if side.upper() in ["LONG", "BUY"] else "SHORT",
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": gross_pnl,
                "fee": fee,
                "funding": funding,
                "exit_reason": f"AUDIT_{reason}",
                "session_id": session_id,
                "notional": qty * entry_price,
            }

            self.record_trade(trade_data)
            logger.warning(f"🔍 Historian: External closure recorded for {symbol} ({reason}) | PnL: {net_pnl:+.4f}")
            return trade_id
        except Exception as e:
            logger.error(f"❌ Historian: Error recording external closure: {e}")
            return None

    # Phase 32: Clean exit reasons for Strategy PnL vs Error Recovery
    # Phase 81: Expanded to include Reconciliation and Drain reasons
    # Phase 82: Added TP_SL_HIT for positions closed by TP/SL before manual close
    CLEAN_EXIT_REASONS = (
        "TP",
        "SL",
        "MANUAL",
        "TIMEOUT",
        "TIME_EXIT",
        "TP_SL_HIT",  # Position already closed (Race)
        "TP (Recon)",  # Recovered by Auditor
        "SL (Recon)",  # Recovered by Auditor
        "DRAIN_PANIC",  # Scheduled Exit
        "DRAIN_AGGRESSIVE",  # Scheduled Exit
        "DRAIN_OPTIMISTIC_ESCALATION",
        "DRAIN_DEFENSIVE_ESCALATION",
        "DRAIN_AGGRESSIVE_ESCALATION",
        "DRAIN_PANIC_ESCALATION",
        "AUDIT_GHOST_REMOVAL",  # Auditor removed stale state
        "AUDIT_RECON_FORCE",  # Auditor forced exchange close
        "LIQUIDATION",  # Detected external closure
        "SHADOW_SL",  # Phase 241: In-memory stop loss
        "BREAKEVEN",  # Phase 241: Breakeven protection
        "TRAILING_STOP",  # Phase 241: Dynamic trailing stop
        "COMMISSION",  # Ledger Sync
        "FUNDING_FEE",  # Ledger Sync
        "INSURANCE_CLEAR",  # Ledger Sync
        "ADJUSTMENT",  # Ledger Sync
    )

    def get_session_stats(self, session_id: Optional[str] = None) -> Any:
        """
        Returns statistics for the current database state, optionally filtered by session. (Non-blocking)
        """
        return self._run_async(self._get_session_stats_sync, session_id)

    def get_setup_stats(self, session_id: Optional[str] = None) -> Any:
        """
        Returns statistics grouped by setup_type. (Non-blocking)
        """
        return self._run_async(self._get_setup_stats_sync, session_id)

    def _get_session_stats_sync(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Internal synchronous stats calculation."""
        """
        Returns statistics for the current database state, optionally filtered by session.

        Phase 32: Separates clean trades (TP, SL, MANUAL) from error recovery trades
        to distinguish Strategy performance from execution issues.
        """
        try:
            params = []
            query = """
                SELECT
                    COUNT(*) as count,
                    SUM(net_pnl) as total_net_pnl,
                    SUM(gross_pnl) as total_gross_pnl,
                    SUM(fee) as total_fees,
                    SUM(funding) as total_funding,
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END) as losses,

                    -- Alpha Attribution (Phase 102)
                    SUM(CASE WHEN lifecycle_phase = 'ACTIVE' THEN net_pnl ELSE 0 END) as active_pnl,
                    SUM(CASE WHEN lifecycle_phase = 'ACTIVE' THEN 1 ELSE 0 END) as active_count,
                    SUM(CASE WHEN lifecycle_phase LIKE 'DRAIN_%' THEN net_pnl ELSE 0 END) as drain_pnl,
                    SUM(CASE WHEN lifecycle_phase LIKE 'DRAIN_%' THEN 1 ELSE 0 END) as drain_count,

                    -- Phase 61: Intelligent PnL Attribution
                    -- Strategy PnL = Clean + Healed
                    SUM(CASE WHEN (exit_reason IN ('TP', 'SL', 'MANUAL', 'TIMEOUT', 'TIME_EXIT', 'TP_SL_HIT', 'TP (Recon)', 'SL (Recon)', 'DRAIN_PANIC', 'DRAIN_AGGRESSIVE', 'DRAIN_OPTIMISTIC_ESCALATION', 'DRAIN_DEFENSIVE_ESCALATION', 'DRAIN_AGGRESSIVE_ESCALATION', 'DRAIN_PANIC_ESCALATION', 'AUDIT_GHOST_REMOVAL', 'AUDIT_RECON_FORCE', 'LIQUIDATION', 'SHADOW_SL', 'BREAKEVEN', 'TRAILING_STOP', 'COMMISSION', 'FUNDING_FEE', 'INSURANCE_CLEAR', 'ADJUSTMENT') OR healed=1) THEN net_pnl ELSE 0 END) as strategy_pnl,
                    SUM(CASE WHEN (exit_reason IN ('TP', 'SL', 'MANUAL', 'TIMEOUT', 'TIME_EXIT', 'TP_SL_HIT', 'TP (Recon)', 'SL (Recon)', 'DRAIN_PANIC', 'DRAIN_AGGRESSIVE', 'DRAIN_OPTIMISTIC_ESCALATION', 'DRAIN_DEFENSIVE_ESCALATION', 'DRAIN_AGGRESSIVE_ESCALATION', 'DRAIN_PANIC_ESCALATION', 'AUDIT_GHOST_REMOVAL', 'AUDIT_RECON_FORCE', 'LIQUIDATION', 'SHADOW_SL', 'BREAKEVEN', 'TRAILING_STOP', 'COMMISSION', 'FUNDING_FEE', 'INSURANCE_CLEAR', 'ADJUSTMENT') OR healed=1) THEN 1 ELSE 0 END) as strategy_count,

                    -- Resilience PnL (Subset of Strategy) = Healed Trades
                    SUM(CASE WHEN healed=1 THEN net_pnl ELSE 0 END) as healed_pnl,
                    SUM(CASE WHEN healed=1 THEN 1 ELSE 0 END) as healed_count,

                    -- Error/Leakage PnL = True Errors (Ghosts, Force Closes, Audits)
                    SUM(CASE WHEN ((exit_reason NOT IN ('TP', 'SL', 'MANUAL', 'TIMEOUT', 'TIME_EXIT', 'TP_SL_HIT', 'TP (Recon)', 'SL (Recon)', 'DRAIN_PANIC', 'DRAIN_AGGRESSIVE', 'DRAIN_OPTIMISTIC_ESCALATION', 'DRAIN_DEFENSIVE_ESCALATION', 'DRAIN_AGGRESSIVE_ESCALATION', 'DRAIN_PANIC_ESCALATION', 'AUDIT_GHOST_REMOVAL', 'AUDIT_RECON_FORCE', 'LIQUIDATION', 'SHADOW_SL', 'BREAKEVEN', 'TRAILING_STOP', 'COMMISSION', 'FUNDING_FEE', 'INSURANCE_CLEAR', 'ADJUSTMENT') AND healed=0)) THEN net_pnl ELSE 0 END) as error_pnl,
                    SUM(CASE WHEN ((exit_reason NOT IN ('TP', 'SL', 'MANUAL', 'TIMEOUT', 'TIME_EXIT', 'TP_SL_HIT', 'TP (Recon)', 'SL (Recon)', 'DRAIN_PANIC', 'DRAIN_AGGRESSIVE', 'DRAIN_OPTIMISTIC_ESCALATION', 'DRAIN_DEFENSIVE_ESCALATION', 'DRAIN_AGGRESSIVE_ESCALATION', 'DRAIN_PANIC_ESCALATION', 'AUDIT_GHOST_REMOVAL', 'AUDIT_RECON_FORCE', 'LIQUIDATION', 'SHADOW_SL', 'BREAKEVEN', 'TRAILING_STOP', 'COMMISSION', 'FUNDING_FEE', 'INSURANCE_CLEAR', 'ADJUSTMENT') AND healed=0)) THEN 1 ELSE 0 END) as error_count,

                    -- Phase 10: Signal-to-Wire (Decision Birth to Wire)
                    -- We use T1 (Decision) instead of T0 (Sensor) for HFT audit
                    AVG((t2_submit_ts - t1_decision_ts) * 1000) as avg_signal_to_wire,
                    MAX((t2_submit_ts - t1_decision_ts) * 1000) as max_signal_to_wire,
                    AVG((t4_fill_ts - t2_submit_ts) * 1000) as avg_external_latency,
                    MAX((t4_fill_ts - t2_submit_ts) * 1000) as max_external_latency,

                    -- Strategy Aggregation Wait (T0 to T1)
                    AVG((t1_decision_ts - t0_signal_ts) * 1000) as avg_strat_wait,

                    -- Phase 240: HFT Core Efficiency (Percent sub-ms)
                    SUM(CASE WHEN (t2_submit_ts - t1_decision_ts) < 0.001 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as hft_efficiency

                FROM trades
            """
            if session_id:
                query += " WHERE session_id = ?"
                params.append(session_id)

            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                row = cursor.fetchone()
                stats = (
                    dict(row)
                    if row and row["count"] > 0
                    else {
                        "count": 0,
                        "total_net_pnl": 0.0,
                        "total_gross_pnl": 0.0,
                        "total_fees": 0.0,
                        "total_funding": 0.0,
                        "wins": 0,
                        "losses": 0,
                        "strategy_pnl": 0.0,
                        "strategy_count": 0,
                        "healed_pnl": 0.0,
                        "healed_count": 0,
                        "error_pnl": 0.0,
                        "drain_pnl": 0.0,
                        "drain_count": 0,
                        "avg_signal_to_wire": 0.0,
                        "max_signal_to_wire": 0.0,
                        "avg_external_latency": 0.0,
                        "max_external_latency": 0.0,
                        "hft_efficiency": 0.0,
                    }
                )

                # Phase 110: Legacy Noise Detection
                # Capture records that were found on exchange but belong to previous timeframes
                legacy_cursor = conn.execute(
                    "SELECT COUNT(*) as count, SUM(net_pnl) as pnl FROM trades WHERE session_id = 'LEGACY_AUDIT'"
                )
                legacy_row = legacy_cursor.fetchone()
                stats["legacy_count"] = legacy_row["count"] or 0
                stats["legacy_pnl"] = legacy_row["pnl"] or 0.0

                return stats
        except Exception as e:
            logger.error(f"❌ Historian: Error getting stats: {e}")
            return {}

    def _get_setup_stats_sync(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Internal synchronous setup stats calculation."""
        try:
            params = []
            query = """
                SELECT
                    setup_type,
                    COUNT(*) as count,
                    SUM(net_pnl) as total_net_pnl,
                    SUM(gross_pnl) as total_gross_pnl,
                    SUM(fee) as total_fees,
                    SUM(funding) as total_funding,
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                    AVG(bars_held) as avg_duration,
                    SUM(CASE WHEN (exit_reason IN ('TP', 'SL', 'MANUAL', 'TIMEOUT', 'TIME_EXIT', 'TP_SL_HIT', 'TP (Recon)', 'SL (Recon)', 'DRAIN_PANIC', 'DRAIN_AGGRESSIVE', 'DRAIN_OPTIMISTIC_ESCALATION', 'DRAIN_DEFENSIVE_ESCALATION', 'DRAIN_AGGRESSIVE_ESCALATION', 'DRAIN_PANIC_ESCALATION', 'AUDIT_GHOST_REMOVAL', 'AUDIT_RECON_FORCE', 'LIQUIDATION', 'SHADOW_SL', 'BREAKEVEN', 'TRAILING_STOP', 'COMMISSION', 'FUNDING_FEE', 'INSURANCE_CLEAR', 'ADJUSTMENT') OR healed=1) THEN net_pnl ELSE 0 END) as strategy_pnl
                FROM trades
            """
            if session_id:
                query += " WHERE session_id = ?"
                params.append(session_id)

            query += " GROUP BY setup_type ORDER BY total_net_pnl DESC"

            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Historian: Error getting setup stats: {e}")
            return []

    def get_error_breakdown(self, session_id: Optional[str] = None) -> Any:
        """Returns a breakdown of error reasons. (Non-blocking)"""
        return self._run_async(self._get_error_breakdown_sync, session_id)

    def _get_error_breakdown_sync(self, session_id: Optional[str] = None) -> Dict[str, int]:
        """Internal synchronous breakdown calculation."""
        """Returns a breakdown of error reasons (e.g. AUDIT_GHOST: 78)."""
        try:
            params = []
            query = """
                SELECT exit_reason, COUNT(*) as count
                FROM trades
                WHERE ((exit_reason NOT IN ('TP', 'SL', 'MANUAL', 'TIMEOUT', 'TIME_EXIT', 'TP_SL_HIT', 'TP (Recon)', 'SL (Recon)', 'DRAIN_PANIC', 'DRAIN_AGGRESSIVE', 'DRAIN_OPTIMISTIC_ESCALATION', 'DRAIN_DEFENSIVE_ESCALATION', 'DRAIN_AGGRESSIVE_ESCALATION', 'DRAIN_PANIC_ESCALATION', 'AUDIT_GHOST_REMOVAL', 'AUDIT_RECON_FORCE', 'LIQUIDATION', 'SHADOW_SL', 'BREAKEVEN', 'TRAILING_STOP', 'COMMISSION', 'FUNDING_FEE', 'INSURANCE_CLEAR', 'ADJUSTMENT') AND healed=0))
            """
            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)

            query += " GROUP BY exit_reason"

            with self._get_conn() as conn:
                cursor = conn.execute(query, params)
                return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"❌ Historian: Error getting breakdown: {e}")
            return {}

    def get_detailed_report(self, session_id: Optional[str] = None) -> Any:
        """Returns a detailed report grouped by symbol. (Non-blocking)"""
        return self._run_async(self._get_detailed_report_sync, session_id)

    def _get_detailed_report_sync(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Internal synchronous detailed report calculation."""
        """Returns a detailed report grouped by symbol and setup_type, optionally filtered by session."""
        try:
            with self._get_conn() as conn:
                query = """
                    SELECT
                        symbol,
                        setup_type,
                        COUNT(*) as trades,
                        SUM(net_pnl) as net_pnl,
                        SUM(fee) as fees,
                        SUM(funding) as funding,
                        AVG(bars_held) as avg_duration,
                        SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
                    FROM trades
                """
                params = []
                if session_id:
                    query += " WHERE session_id = ?"
                    params.append(session_id)

                query += " GROUP BY symbol, setup_type ORDER BY net_pnl DESC"

                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Historian: Error getting detailed report: {e}")
            return []

    def run_integrity_check(self) -> Dict[str, Any]:
        """Performs a mathematical integrity check on all records."""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT trade_id, gross_pnl, fee, funding, net_pnl, entry_price, exit_price FROM trades"
                )
                rows = cursor.fetchall()

            issues = []
            checked = 0
            for row in rows:
                checked += 1
                # Check 1: Net PnL Identity
                expected_net = row["gross_pnl"] - row["fee"] - row["funding"]
                if abs(row["net_pnl"] - expected_net) > 0.0001:
                    issues.append(
                        f"Trade {row['trade_id']}: Net PnL mismatch (Expected {expected_net}, Got {row['net_pnl']})"
                    )

                # Check 2: Missing Prices
                if row["entry_price"] <= 0 or row["exit_price"] <= 0:
                    issues.append(
                        f"Trade {row['trade_id']}: Invalid price detection (Entry={row['entry_price']}, Exit={row['exit_price']})"
                    )

            return {"status": "PASS" if not issues else "FAIL", "trades_checked": checked, "issues": issues}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def export_to_csv(self, target_path: str):
        """Exports all trades to a CSV file."""
        import csv

        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM trades ORDER BY id DESC")
                rows = cursor.fetchall()

            if not rows:
                print("⚠️ No trades found to export.")
                return False

            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            keys = rows[0].keys()
            with open(target_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))

            print(f"✅ Exported {len(rows)} trades to {target_path}")
            return True
        except Exception as e:
            print(f"❌ Export failed: {e}")
            return False

    def clear_history(self):
        """
        Wipes all trade history to start fresh.
        Use with caution (e.g. strategy reset).
        """
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM trades")
                conn.commit()
            logger.warning("🗑️ Historian: Trade history cleared manually.")
            return True
        except Exception as e:
            logger.error(f"❌ Historian: Error clearing history: {e}")
            return False


# Global instance
historian = TradeHistorian()


async def main_cli():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Casino-V3 Trade Historian Audit Tool")
    parser.add_argument("--report", action="store_true", help="Show summary report")
    parser.add_argument("--details", action="store_true", help="Show detailed report by symbol")
    parser.add_argument("--check", action="store_true", help="Run integrity check")
    parser.add_argument("--export", type=str, help="Export trades to CSV file path")
    parser.add_argument("--clear", action="store_true", help="Wipe all trade history (DANGER)")
    parser.add_argument("--session", type=str, help="Filter reports by specific session ID")

    args = parser.parse_args()

    if args.report:
        stats = await historian.get_session_stats(session_id=args.session)
        print("\n📊 SESSION SUMMARY REPORT")
        if args.session:
            print(f"Filter: {args.session}")
        print("==========================")
        print(f"Total Trades: {stats['count']}")
        print(f"Net PnL:      {stats['total_net_pnl']:+.4f} USDT")
        print(f"Gross PnL:    {stats['total_gross_pnl']:+.4f} USDT")
        print(f"Total Fees:   {stats['total_fees']:.4f} USDT")
        print(
            f"Win Rate:     {(stats['wins'] * 100 / stats['count'] if stats['count'] > 0 else 0):.2f}% ({stats['wins']}W / {stats['losses']}L)"
        )
        print("--------------------------")
        print("⚡ HFT PERFORMANCE AUDIT")
        print(f"Signal-to-Wire (Avg): {stats.get('avg_signal_to_wire', 0) or 0:.3f} ms")
        print(f"Signal-to-Wire (Max): {stats.get('max_signal_to_wire', 0) or 0:.3f} ms")
        print(f"HFT Core Efficiency:  {stats.get('hft_efficiency', 0) or 0:.1f}% (sub-1ms)")
        print(f"Strategy Agg. Wait:   {stats.get('avg_strat_wait', 0) or 0:.1f} ms")
        print("--------------------------")
        print("🌍 NETWORK LATENCY")
        print(f"External/Exchange (Avg): {stats.get('avg_external_latency', 0) or 0:.1f} ms")
        print(f"External/Exchange (Max): {stats.get('max_external_latency', 0) or 0:.1f} ms")
        print("==========================\n")

    if args.details:
        details = await historian.get_detailed_report(session_id=args.session)
        print("\n📋 DETAILED SYMBOL REPORT")
        print("==========================")
        print(f"{'Symbol':<15} {'Trades':<8} {'Net PnL':<12} {'Win%':<8} {'Dur.'}")
        for d in details:
            print(
                f"{d['symbol']:<15} {d['trades']:<8} {d['net_pnl']:<12.4f} {d['win_rate']:<8.2f} {d['avg_duration']:.1f}"
            )
        print("==========================\n")

    if args.check:
        audit = historian.run_integrity_check()
        print(f"\n🔍 INTEGRITY AUDIT: {audit['status']}")
        print(f"Checked {audit['trades_checked']} records.")
        if audit["issues"]:
            print("Issues found:")
            for issue in audit["issues"]:
                print(f"  - {issue}")
        else:
            print("✅ All mathematical identities are correct.")
        print("")

    if args.export:
        historian.export_to_csv(args.export)

    if args.clear:
        confirm = input("⚠️ Are you sure you want to WIPE all trade history? (y/N): ")
        if confirm.lower() == "y":
            historian.clear_history()
            print("🗑️ History cleared.")
        else:
            print("Aborted.")

    if len(sys.argv) == 1:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main_cli())
