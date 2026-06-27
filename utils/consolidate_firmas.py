import json
import os
import sqlite3
import sys
from collections import defaultdict

import numpy as np

# Asegurar que podemos importar desde la raíz
sys.path.insert(0, ".")
from utils.cluster_builder import compute_metrics_from_db


def consolidate_firmas():
    ready_dir = "data/datasets/daily_backtest_ready"
    all_metrics = defaultdict(list)

    if not os.path.exists(ready_dir):
        print(f"❌ Directorio no encontrado: {ready_dir}")
        return

    for db_file in os.listdir(ready_dir):
        if not db_file.endswith(".db"):
            continue

        # Extraer símbolo. Manejar formatos LTC_REGIMEN_FECHA.db y FECHA_SYMBOL.db
        if "LTC_" in db_file:
            symbol = "LTCUSDT"
        elif "_" in db_file:
            # Buscar el formato FECHA_SYMBOL.db, ej: 2024-05-01_OPUSDT.db
            parts = db_file.split("_")
            symbol = parts[-1].replace(".db", "")
        else:
            symbol = db_file.replace(".db", "")

        conn = sqlite3.connect(os.path.join(ready_dir, db_file))
        # Usar la función importada fuera del loop
        metrics = compute_metrics_from_db(conn, symbol)
        conn.close()

        if metrics:
            # Verificar si todas las métricas necesarias son numéricas
            valid = True
            for k, v in metrics.items():
                if v is None:
                    valid = False
                    break

            if valid:
                all_metrics[symbol].append(metrics)
                print(f"    ✅ Procesado {db_file} para {symbol}")
            else:
                # Loggear específicamente qué falló
                missing = [k for k, v in metrics.items() if v is None]
                print(f"    ⚠️ Saltado {db_file} (datos faltantes: {missing})")
        else:
            print(f"    ⚠️ Saltado {db_file} (no se pudieron computar métricas)")

    # Calcular medias
    firmas = {}
    for symbol, list_metrics in all_metrics.items():
        avg = {
            dim: float(np.mean([m[dim] for m in list_metrics]))
            for dim in ["tick_size_efficiency", "book_density", "volume_vol_ratio", "speed"]
        }
        firmas[symbol] = avg

    with open("config/firmas.json", "w") as f:
        json.dump(firmas, f, indent=2)
    print(f"\n✅ Firmas generadas para {len(firmas)} activos en config/firmas.json")


if __name__ == "__main__":
    consolidate_firmas()
