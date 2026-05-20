import json
import sqlite3

DB_PATH = "data/historian.db"


def main():
    conn = sqlite3.connect(DB_PATH)

    symbols = ["AVAXUSDT", "SOLUSDT", "LTCUSDT"]

    for sym in symbols:
        print(f"\n--- REGIME ANALYSIS FOR {sym} ---")

        signals = conn.execute(
            """
            SELECT timestamp, side, price, metadata FROM signals
            WHERE symbol = ? AND setup_type = 'TacticalAbsorptionV2'
        """,
            (sym,),
        ).fetchall()

        regime_counts = {"WIN": {}, "LOSS": {}, "TIMEOUT": {}}

        for ts, side, price, metadata_str in signals:
            if not metadata_str or price == 0:
                continue

            try:
                meta = json.loads(metadata_str)
            except:
                continue

            setup_name = meta.get("setup_name", "UNKNOWN")

            # Check outcome
            ps = conn.execute(
                "SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
                (sym, ts, ts + 900),
            ).fetchall()
            if not ps:
                continue

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

            reg = "UNKNOWN"
            if "IN_VALUE" in setup_name:
                reg = "IN_VALUE (Balance)"
            elif "OUT_OF_VALUE" in setup_name:
                reg = "OUT_OF_VALUE (Trend)"
            elif "EXCESS" in setup_name:
                reg = "EXCESS (Extremes)"

            if reg not in regime_counts[outcome]:
                regime_counts[outcome][reg] = 0
            regime_counts[outcome][reg] += 1

        for outcome in ["WIN", "LOSS"]:
            print(f"Outcome: {outcome}")
            total = sum(regime_counts[outcome].values())
            for reg, count in sorted(regime_counts[outcome].items()):
                pct = (count / total * 100) if total > 0 else 0
                print(f"  {reg}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
