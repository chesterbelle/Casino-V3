import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

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
                        SUM(funding) as total_funding,
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
                        "total_funding": 0.0,
                        "wins": 0,
                        "losses": 0,
                    }
                )
        except Exception as e:
            logger.error(f"❌ Historian: Error getting stats: {e}")
            return {}

    def get_detailed_report(self) -> List[Dict[str, Any]]:
        """Returns a detailed report grouped by symbol."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT
                        symbol,
                        COUNT(*) as trades,
                        SUM(net_pnl) as net_pnl,
                        SUM(fee) as fees,
                        SUM(funding) as funding,
                        AVG(bars_held) as avg_duration,
                        SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
                    FROM trades
                    GROUP BY symbol
                    ORDER BY net_pnl DESC
                """
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"❌ Historian: Error getting detailed report: {e}")
            return []

    def run_integrity_check(self) -> Dict[str, Any]:
        """Performs a mathematical integrity check on all records."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM trades")
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
            with sqlite3.connect(self.db_path) as conn:
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

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Casino-V3 Trade Historian Audit Tool")
    parser.add_argument("--report", action="store_true", help="Show summary report")
    parser.add_argument("--details", action="store_true", help="Show detailed report by symbol")
    parser.add_argument("--check", action="store_true", help="Run integrity check")
    parser.add_argument("--export", type=str, help="Export trades to CSV file path")
    parser.add_argument("--clear", action="store_true", help="Wipe all trade history (DANGER)")

    args = parser.parse_args()

    if args.report:
        stats = historian.get_session_stats()
        print("\n📊 SESSION SUMMARY REPORT")
        print("==========================")
        print(f"Total Trades: {stats['count']}")
        print(f"Net PnL:      {stats['total_net_pnl']:+.4f} USDT")
        print(f"Gross PnL:    {stats['total_gross_pnl']:+.4f} USDT")
        print(f"Total Fees:   {stats['total_fees']:.4f} USDT")
        print(
            f"Win Rate:     {(stats['wins'] * 100 / stats['count'] if stats['count'] > 0 else 0):.2f}% ({stats['wins']}W / {stats['losses']}L)"
        )
        print("==========================\n")

    if args.details:
        details = historian.get_detailed_report()
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
