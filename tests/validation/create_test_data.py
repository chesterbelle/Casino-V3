#!/usr/bin/env python3
"""
Script para crear datos de prueba para validación de backtesting.

Genera un CSV con datos OHLCV simulados para testing.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def create_test_data(num_candles=10, start_price=100000):
    """
    Crea datos OHLCV simulados.

    Args:
        num_candles: Número de velas a generar
        start_price: Precio inicial

    Returns:
        DataFrame con datos OHLCV
    """
    data = []
    current_time = datetime.now()
    current_price = start_price

    for i in range(num_candles):
        # Simular movimiento de precio (±1%)
        change = current_price * 0.01 * (0.5 - np.random.random())
        open_price = current_price
        high_price = open_price + abs(change)
        low_price = open_price - abs(change)
        close_price = open_price + change

        data.append(
            {
                "timestamp": int((current_time + timedelta(minutes=i)).timestamp() * 1000),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 100 + np.random.random() * 50,
            }
        )

        current_price = close_price

    df = pd.DataFrame(data)
    return df


if __name__ == "__main__":
    import sys

    num_candles = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    output_file = sys.argv[2] if len(sys.argv) > 2 else "test_data.csv"

    print(f"📊 Generando {num_candles} velas de datos de prueba...")

    df = create_test_data(num_candles)

    df.to_csv(output_file, index=False)

    print(f"✅ Datos guardados en: {output_file}")
    print(f"📈 Rango de precios: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
    print(f"📊 Volumen total: {df['volume'].sum():.2f}")
