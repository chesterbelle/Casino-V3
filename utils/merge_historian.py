import glob
import os
import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE, parent_trade_id TEXT, symbol TEXT, side TEXT,
    entry_price REAL, exit_price REAL, qty REAL, fee REAL DEFAULT 0.0,
    funding REAL DEFAULT 0.0, gross_pnl REAL, net_pnl REAL,
    exit_reason TEXT, timestamp TEXT, bars_held INTEGER, session_id TEXT,
    healed BOOLEAN DEFAULT 0, t4_fill_ts REAL, slippage_pct REAL,
    lifecycle_phase TEXT DEFAULT 'ACTIVE', setup_type TEXT DEFAULT 'unknown',
    level_ref TEXT DEFAULT 'unknown', level_price REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS price_candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL, symbol TEXT, open REAL, high REAL, low REAL,
    close REAL, volume REAL
);
CREATE TABLE IF NOT EXISTS decision_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL,
    symbol TEXT,
    status TEXT,
    gate TEXT,
    reason TEXT,
    metrics TEXT,
    price REAL,
    side TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL, symbol TEXT, side TEXT, setup_type TEXT, price REAL,
    metadata TEXT, session_id TEXT, trace_id TEXT
);
CREATE TABLE IF NOT EXISTS price_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT, timestamp REAL, price REAL, micro_z REAL,
    trade_id TEXT
);
"""


def merge_databases():
    master_db = "data/historian.db"
    print(f"🔗 Fusing temporary databases into Master: {master_db}...")

    os.makedirs(os.path.dirname(master_db), exist_ok=True)

    tables = ["trades", "price_candles", "decision_traces", "signals", "price_samples"]

    temp_dbs = glob.glob("data/historian_*.db")
    if not temp_dbs:
        print("⚠️ No temporary databases found to merge.")
        return

    conn = sqlite3.connect(master_db)
    conn.execute("PRAGMA journal_mode=WAL;")

    # Ensure master has schema before merging
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    total_merged = {table: 0 for table in tables}

    for temp_db in temp_dbs:
        if temp_db == master_db:
            continue
        print(f"📦 Processing: {temp_db}...")

        try:
            conn.execute(f"ATTACH DATABASE '{temp_db}' AS temp_db;")
        except sqlite3.OperationalError as e:
            print(f"  ⚠️ Skipping corrupt DB: {e}")
            continue

        for table in tables:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM temp_db.{table}")
                row_count = cursor.fetchone()[0]
                if row_count == 0:
                    continue

                columns_cursor = conn.execute(f"PRAGMA table_info({table})")
                master_cols = [col[1] for col in columns_cursor.fetchall() if col[1] != "id"]
                temp_cols = {
                    col[1] for col in conn.execute(f"PRAGMA temp_db.table_info({table})").fetchall() if col[1] != "id"
                }
                select_exprs = []
                for col in master_cols:
                    if col in temp_cols:
                        select_exprs.append(col)
                    else:
                        select_exprs.append(f"NULL AS {col}")
                cols_str = ", ".join(master_cols)
                select_str = ", ".join(select_exprs)
                conn.execute(f"INSERT OR IGNORE INTO {table} ({cols_str}) SELECT {select_str} FROM temp_db.{table}")
                total_merged[table] += row_count
            except sqlite3.OperationalError:
                pass

        conn.commit()
        conn.execute("DETACH DATABASE temp_db;")

    conn.commit()

    # Verify data was actually merged before deleting sources
    total_rows = sum(total_merged.values())
    if total_rows == 0:
        conn.close()
        print("\n⚠️ No rows merged — keeping source databases.")
        return

    conn.close()

    for temp_db in temp_dbs:
        if temp_db == master_db:
            continue
        try:
            os.remove(temp_db)
            for ext in ["-wal", "-shm"]:
                if os.path.exists(temp_db + ext):
                    os.remove(temp_db + ext)
        except Exception as e:
            print(f"⚠️ Failed to remove temporary file {temp_db}: {e}")

    print("\n🏁 CONSOLIDATION COMPLETE")
    for table, count in total_merged.items():
        print(f"  ✅ {table:16s}: Merged {count} rows")


if __name__ == "__main__":
    merge_databases()
