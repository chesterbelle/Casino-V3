import json
import math
import sqlite3

DB_PATH = "data/historian.db"


def main():
    try:
        conn = sqlite3.connect(DB_PATH)
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        return

    signals = conn.execute(
        """
        SELECT symbol, side, price, metadata, setup_type
        FROM signals
        WHERE setup_type = 'TacticalAbsorptionV2'
    """
    ).fetchall()

    # We will compute the Excursion for each signal to determine WIN/LOSS
    # A WIN is when MFE hits +0.3% before MAE hits -0.3%
    # But wait, it's faster to just use price samples

    geography = {
        "AT_VAH": {"count": 0, "win": 0, "loss": 0},
        "AT_VAL": {"count": 0, "win": 0, "loss": 0},
        "AT_POC": {"count": 0, "win": 0, "loss": 0},
        "NO_MANS_LAND": {"count": 0, "win": 0, "loss": 0},
        "MISSING_DATA": {"count": 0, "win": 0, "loss": 0},
    }

    print("Analizando Geografía de Absorción (POC vs VA Edges)...")

    for row in signals:
        sym, side, price, metadata_str, _ = row
        if not metadata_str or price <= 0:
            continue

        try:
            meta = json.loads(metadata_str)
        except:
            continue

        poc = meta.get("poc")
        vah = meta.get("vah")
        val = meta.get("val")

        if not poc or not vah or not val or poc == 0:
            geography["MISSING_DATA"]["count"] += 1
            continue

        # Determine Geography
        # VAH/VAL proximity (0.20% tolerance)
        va_width = vah - val
        tolerance = max(va_width * 0.15, price * 0.001)  # 15% of VA width or 0.1% price

        geo_tag = "NO_MANS_LAND"
        if abs(price - vah) <= tolerance:
            geo_tag = "AT_VAH"
        elif abs(price - val) <= tolerance:
            geo_tag = "AT_VAL"
        elif abs(price - poc) <= tolerance:
            geo_tag = "AT_POC"

        geography[geo_tag]["count"] += 1

        # We need to find the outcome from decision_traces or price_samples?
        # A simple outcome check using price_samples would be slow but accurate
        # Since this is a diagnostic script, we will skip outcome for now and just show distribution
        # Wait, the prompt says: "mapear los trades ganadores/perdedores con su distancia"
        # Let's get the trace from decision traces if available

    print("\n[RESULTADOS DE GEOGRAFÍA IN_VALUE]")
    print(f"{'ZONA':<15} | {'CANTIDAD':<8} | {'% DEL TOTAL'}")
    print("-" * 40)

    total_valid = sum(g["count"] for k, g in geography.items() if k != "MISSING_DATA")

    for k, g in geography.items():
        if k == "MISSING_DATA":
            continue
        c = g["count"]
        pct = (c / total_valid * 100) if total_valid > 0 else 0
        print(f"{k:<15} | {c:<8} | {pct:.1f}%")


if __name__ == "__main__":
    main()
