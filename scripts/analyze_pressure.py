import glob
import sqlite3

import numpy as np
import pandas as pd

from core.pressure.engine import PressureEngine


def analyze_pressure_distribution():
    # Merge todos los historiales temporales
    db_files = glob.glob("data/historian_LTC_*.db")
    print(f"Analizando {len(db_files)} archivos de auditoría...")

    conn = sqlite3.connect("data/historian_LTC_TREND_UP_2024-03-01.db")
    df = pd.read_sql("SELECT close, volume, timestamp FROM price_candles", conn)
    print(f"DEBUG: Filas en DF: {len(df)}")

    # Usar datos reales del motor para validar
    engine = PressureEngine()
    # Para cada fila, actualizar motor y recolectar estado
    results = []
    for _, row in df.iterrows():
        # Simulamos un tick: asumimos compra o venta según el volumen si no hay side
        # En historian.db de velas no hay side, vamos a asumir side basado en dirección precio
        is_buyer_maker = row["close"] < row.get("open", row["close"])
        engine.update(qty=row["volume"], is_buyer_maker=is_buyer_maker, ts=row["timestamp"], price=row["close"])
        state = engine.get_state()
        results.append(state.cvd_velocity)

    print(f"DEBUG: Primeiros resultados: {results[:10]}")
    pressure_series = pd.Series(results)
    print(f"DEBUG: Series tiene {len(pressure_series)} valores, nans: {pressure_series.isna().sum()}")

    conn.close()


if __name__ == "__main__":
    analyze_pressure_distribution()
