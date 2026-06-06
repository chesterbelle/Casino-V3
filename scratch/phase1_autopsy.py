import json
import sqlite3
import statistics

DB_PATH = "data/historian.db"


def main():
    conn = sqlite3.connect(DB_PATH)

    symbols_of_interest = ["AVAXUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT"]

    signals = conn.execute(
        """
        SELECT timestamp, symbol, side, price, metadata
        FROM signals
        WHERE setup_type = 'tactical_absorption' AND symbol IN (?, ?, ?, ?)
        ORDER BY timestamp
    """,
        symbols_of_interest,
    ).fetchall()

    stats = {
        sym: {
            "WIN": {"atr": [], "fp_z": [], "entry_z": []},
            "LOSS": {"atr": [], "fp_z": [], "entry_z": []},
            "TIMEOUT": {"atr": [], "fp_z": [], "entry_z": []},
        }
        for sym in symbols_of_interest
    }

    for ts, sym, side, price, metadata_str in signals:
        if not metadata_str:
            continue
        try:
            meta = json.loads(metadata_str)
        except:
            continue

        atr = meta.get("atr_1m", 0)
        fp_z = meta.get("footprint_z_score", 0)
        entry_z = meta.get("z_score_entry", 0)

        # Calculate outcome based on 0.3% TP / 0.3% SL within 900s
        ps = conn.execute(
            "SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
            (sym, ts, ts + 900),
        ).fetchall()

        outcome = "TIMEOUT"
        for (p,) in ps:
            m = (p - price) / price * 100
            if side == "SHORT":
                m = -m

            if m >= 0.3:
                outcome = "WIN"
                break
            elif m <= -0.3:
                outcome = "LOSS"
                break

        stats[sym][outcome]["atr"].append(atr)
        stats[sym][outcome]["fp_z"].append(abs(fp_z))
        stats[sym][outcome]["entry_z"].append(entry_z)

    print("PHASE 1: VOLATILITY & Z-SCORE PROFILING")
    print(f"{'Symbol':<10} | {'Result':<7} | {'Count':<5} | {'Avg ATR%':<9} | {'Avg FP Z':<9} | {'Avg Micro Z':<11}")
    print("-" * 65)

    for sym in symbols_of_interest:
        for result in ["WIN", "LOSS"]:
            d = stats[sym][result]
            n = len(d["atr"])
            if n == 0:
                continue

            avg_atr = statistics.mean(d["atr"])
            avg_fp_z = statistics.mean(d["fp_z"])
            avg_entry_z = statistics.mean(d["entry_z"])

            print(f"{sym:<10} | {result:<7} | {n:<5} | {avg_atr:>8.3f}% | {avg_fp_z:>9.2f} | {avg_entry_z:>11.2f}")
        print("-" * 65)


if __name__ == "__main__":
    main()
