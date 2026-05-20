import glob
import os
import sqlite3

def merge_databases():
    master_db = "data/historian.db"
    print(f"🔗 Fusing temporary databases into Master: {master_db}...")

    # Ensure master directory exists
    os.makedirs(os.path.dirname(master_db), exist_ok=True)

    # Tables to consolidate
    tables = ["trades", "price_candles", "decision_traces", "signals", "price_samples"]

    # Find all isolated database files
    temp_dbs = glob.glob("data/historian_*.db")
    if not temp_dbs:
        print("⚠️ No temporary databases found to merge.")
        return

    # Connect to the master database
    conn = sqlite3.connect(master_db)
    
    # Enable WAL mode for performance
    conn.execute("PRAGMA journal_mode=WAL;")

    total_merged = {table: 0 for table in tables}

    for temp_db in temp_dbs:
        print(f"📦 Processing: {temp_db}...")
        
        # Attach the temporary database
        conn.execute(f"ATTACH DATABASE '{temp_db}' AS temp_db;")

        for table in tables:
            # Check if table exists in temporary database
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM temp_db.{table}")
                row_count = cursor.fetchone()[0]
                if row_count == 0:
                    continue

                # Get column list of the table in the master DB to avoid mismatched schemas
                columns_cursor = conn.execute(f"PRAGMA table_info({table})")
                cols = [col[1] for col in columns_cursor.fetchall() if col[1] != 'id']  # Skip auto-increment ID
                cols_str = ", ".join(cols)

                # Bulk insert from temporary to master
                conn.execute(f"INSERT OR IGNORE INTO {table} ({cols_str}) SELECT {cols_str} FROM temp_db.{table}")
                total_merged[table] += row_count
            except sqlite3.OperationalError as e:
                # Table might not exist in the temp DB (e.g. if no candles were generated)
                pass

        conn.execute("DETACH DATABASE temp_db;")

    conn.commit()
    conn.close()

    # Clean up temporary database files only after successful commit
    for temp_db in temp_dbs:
        try:
            os.remove(temp_db)
            # Also clean up SQLite WAL/SHM files if they exist
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
