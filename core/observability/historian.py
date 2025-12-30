import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger("TradeHistorian")


class TradeHistorian:
    """
    Persistent trade historian using SQLite.
    Tracks every trade with precision accounting (Fees, Funding, Net PnL).
    """

    def __init__(self, db_path: str = "data/casino_v3.db"):
        self.db_path = db_path
        self._ensure_data_dir()
        self._init_db()

    def _ensure_data_dir(self):
        """Ensures the directory for the database exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_db(self):
        """Initializes the database schema."""
        with sqlite3.connect(self.db_path) as conn:
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
                    bars_held INTEGER
                )
            """
            )
            conn.commit()

    def record_trade(self, trade_data: Dict[str, Any]):
        """
        Records a completed trade into the database.

        Expected trade_data keys:
        - trade_id, symbol, side, entry_price, exit_price, notional,
        - pnl (gross), fee, funding, exit_reason, bars_held
        """
        try:
            # Calculate net pnl if not provided
            gross = trade_data.get("pnl", 0.0)
            fee = trade_data.get("fee", 0.0)
            funding = trade_data.get("funding", 0.0)
            net_pnl = gross - fee - funding

            # Estimate qty from notional for accounting
            entry_price = trade_data.get("entry_price", 0.0)
            notional = trade_data.get("notional", 0.0)
            qty = notional / entry_price if entry_price > 0 else 0.0

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trades
                    (trade_id, symbol, side, entry_price, exit_price, qty, fee, funding, gross_pnl, net_pnl, exit_reason, timestamp, bars_held)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        trade_data.get("trade_id"),
                        trade_data.get("symbol"),
                        trade_data.get("side"),
                        entry_price,
                        trade_data.get("exit_price"),
                        qty,
                        fee,
                        funding,
                        gross,
                        net_pnl,
                        trade_data.get("exit_reason"),
                        datetime.now().isoformat(),
                        trade_data.get("bars_held", 0),
                    ),
                )
                conn.commit()
            logger.info(f"💾 Historian: Registered trade {trade_data.get('trade_id')} | Net PnL: {net_pnl:+.4f}")
        except Exception as e:
            logger.error(f"❌ Historian: Error recording trade: {e}")

    def get_session_stats(self) -> Dict[str, Any]:
        """Returns statistics for the current database state."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as count,
                        SUM(net_pnl) as total_net_pnl,
                        SUM(gross_pnl) as total_gross_pnl,
                        SUM(fee) as total_fees,
                        SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END) as losses
                    FROM trades
                """
                )
                row = cursor.fetchone()
                return (
                    dict(row)
                    if row["count"] > 0
                    else {
                        "count": 0,
                        "total_net_pnl": 0.0,
                        "total_gross_pnl": 0.0,
                        "total_fees": 0.0,
                        "wins": 0,
                        "losses": 0,
                    }
                )
        except Exception as e:
            logger.error(f"❌ Historian: Error getting stats: {e}")
            return {}

    def clear_history(self):
        """
        Wipes all trade history to start fresh.
        Use with caution (e.g. strategy reset).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM trades")
                conn.commit()
            logger.warning("🗑️ Historian: Trade history cleared manually.")
            return True
        except Exception as e:
            logger.error(f"❌ Historian: Error clearing history: {e}")
            return False


# Global instance
historian = TradeHistorian()
