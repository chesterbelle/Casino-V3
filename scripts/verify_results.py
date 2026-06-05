import sqlite3


def check_results():
    db_files = [
        "data/historian_LTC_TREND_DOWN_2024-04-01.db",
        "data/historian_LTC_TREND_DOWN_2024-10-01.db",
        "data/historian_LTC_TREND_DOWN_2025-02-01.db",
        "data/historian_LTC_TREND_UP_2024-03-01.db",
    ]

    total_signals = 0
    for db in db_files:
        try:
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM signals")
            count = cursor.fetchone()[0]
            total_signals += count
            print(f"File {db}: {count} signals")
            conn.close()
        except Exception as e:
            print(f"Error reading {db}: {e}")

    print(f"Total signals detected: {total_signals}")


if __name__ == "__main__":
    check_results()
