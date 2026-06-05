import sqlite3


def validate_pressure_engine():
    db_path = "/home/chesterbelle/Casino-V3/data/historian.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Revisemos esquemas de todas las tablas importantes
    for table in ["trades", "signals", "price_candles"]:
        cursor.execute(f"PRAGMA table_info({table})")
        print(f"\nTabla: {table}")
        for row in cursor.fetchall():
            print(row[1])

    conn.close()


if __name__ == "__main__":
    validate_pressure_engine()
