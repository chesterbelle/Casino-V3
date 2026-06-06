import glob
import sqlite3

import pandas as pd

from config.coin_profiles import COIN_PROFILES
from core.pressure.engine import PressureEngine


def calibrate_clusters():
    # Identificar perfiles definidos
    profiles = COIN_PROFILES
    print(f"Calibrando para {len(profiles)} perfiles...")

    # Historias disponibles
    db_files = glob.glob("data/historian_LTC_*.db")
    if not db_files:
        print("No hay bases de datos para calibrar.")
        return

    # Usamos LTC como proxy para calibrar el engine
    # En un escenario real iteraríamos sobre más activos
    conn = sqlite3.connect("data/historian_LTC_TREND_UP_2024-03-01.db")
    df = pd.read_sql("SELECT close, volume FROM price_candles", conn)
    conn.close()

    # Engine para medir presión
    engine = PressureEngine()
    SYM = "LTC/USDT"
    pressure_values = []

    for _, row in df.iterrows():
        engine.update(SYM, qty=row["volume"], is_buyer_maker=False, ts=0, price=row["close"])
        pressure_values.append(engine.get_state(SYM).cvd_velocity)

    pressure_series = pd.Series(pressure_values)

    # Calcular umbrales basados en distribución
    # P90 es un estándar institucional para eventos de alta presión
    p90 = pressure_series.quantile(0.90)
    p75 = pressure_series.quantile(0.75)

    print("\n--- Resultados de Calibración ---")
    print(f"Umbral P90 (Alta presión): {p90:.4f}")
    print(f"Umbral P75 (Presión media): {p75:.4f}")

    return p90, p75


if __name__ == "__main__":
    calibrate_clusters()
