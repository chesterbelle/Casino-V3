import json
import sqlite3

DB_PATH = "data/historian.db"


def main():
    conn = sqlite3.connect(DB_PATH)

    # Let's find the fastest losing trades.
    # To do this, we need to iterate over all signals and find time-to-loss.

    signals = conn.execute(
        """
        SELECT timestamp, symbol, side, price, metadata
        FROM signals
        WHERE setup_type = 'TacticalAbsorptionV2'
    """
    ).fetchall()

    losses = []

    for ts, sym, side, price, metadata_str in signals:
        if not metadata_str or price <= 0:
            continue

        try:
            meta = json.loads(metadata_str)
        except:
            continue

        ps = conn.execute(
            "SELECT timestamp, price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
            (sym, ts, ts + 900),
        ).fetchall()
        if not ps:
            continue

        for p_ts, p in ps:
            m = (p - price) / price * 100
            if side == "SHORT":
                m = -m

            if m >= 0.3:
                # Win before loss
                break
            elif m <= -0.3:
                # Loss
                time_to_loss = p_ts - ts
                losses.append(
                    {
                        "symbol": sym,
                        "side": side,
                        "price": price,
                        "time_to_loss": time_to_loss,
                        "setup_name": meta.get("setup_name", "UNKNOWN"),
                        "poc": meta.get("poc"),
                        "vah": meta.get("vah"),
                        "val": meta.get("val"),
                    }
                )
                break

    # Sort by time_to_loss ascending
    losses.sort(key=lambda x: x["time_to_loss"])

    print("PHASE 3: TOP 50 MOST TOXIC TRADES (Fastest Losses)")
    print(f"{'Symbol':<10} | {'Side':<5} | {'TTL (s)':<7} | {'Setup Name':<40} | {'Value Pos'}")
    print("-" * 90)

    for l in losses[:50]:
        poc = l["poc"]
        vah = l["vah"]
        val = l["val"]
        price = l["price"]

        # Determine Value Pos
        pos = "UNKNOWN"
        if poc and vah and val:
            if price > vah:
                pos = "ABOVE_VA"
            elif price < val:
                pos = "BELOW_VA"
            else:
                pos = "INSIDE_VA"

        print(f"{l['symbol']:<10} | {l['side']:<5} | {l['time_to_loss']:<7.1f} | {l['setup_name']:<40} | {pos}")


if __name__ == "__main__":
    main()
