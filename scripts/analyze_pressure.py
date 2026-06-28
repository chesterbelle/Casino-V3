import glob
import sqlite3

import pandas as pd

from core.order_flow.engine import OrderFlowEngine


def analyze_pressure_distribution():
    # Merge todos los historiales temporales
    db_files = glob.glob("data/historian_LTC_*.db")
    print(f"Analizando {len(db_files)} archivos de auditoría...")

    conn = sqlite3.connect("data/historian_LTC_TREND_UP_2024-03-01.db")
    df = pd.read_sql("SELECT close, volume, timestamp FROM price_candles", conn)
    print(f"DEBUG: Filas en DF: {len(df)}")

    # Usar datos reales del motor para validar
    engine = OrderFlowEngine()
    SYM = "LTC/USDT"
    results = []
    for _, row in df.iterrows():
        is_buyer_maker = row["close"] < row.get("open", row["close"])
        engine.update(SYM, qty=row["volume"], is_buyer_maker=is_buyer_maker, ts=row["timestamp"], price=row["close"])
        state = engine.get_state(SYM)
        results.append(state.cvd_velocity)

    print(f"DEBUG: Primeiros resultados: {results[:10]}")
    pressure_series = pd.Series(results)
    print(f"DEBUG: Series tiene {len(pressure_series)} valores, nans: {pressure_series.isna().sum()}")

    conn.close()


if __name__ == "__main__":
    analyze_pressure_distribution()
