#!/usr/bin/env python3
"""
Análisis MFE/MAE Multi-Horizonte

Analiza la calidad de señales en múltiples horizontes temporales
para identificar el mejor TP/SL y entender el comportamiento real del mercado.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def load_data(filepath):
    """Carga datos de mercado desde CSV."""
    df = pd.read_csv(filepath)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def analyze_multi_horizon(data_path, logs_path, horizons=[10, 30, 60, 120, 240]):
    """
    Analiza MFE/MAE en múltiples horizontes temporales.

    Args:
        data_path: Path al CSV de datos de mercado
        logs_path: Path al JSON de resultados del backtest
        horizons: Lista de horizontes en número de velas
    """
    print(f"📉 Cargando datos de mercado desde {data_path}...")
    df = load_data(data_path)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)

    print(f"📋 Cargando trades desde {logs_path}...")
    with open(logs_path, "r") as f:
        results = json.load(f)

    trades = results.get("closed_trades", [])
    if not trades:
        print("❌ No se encontraron trades en los logs.")
        return

    print(f"\n{'='*80}")
    print(f"🔍 ANÁLISIS MFE/MAE MULTI-HORIZONTE")
    print(f"{'='*80}\n")
    print(f"Total de trades: {len(trades)}")
    print(f"Horizontes a analizar: {horizons} velas\n")

    # Almacenar resultados por horizonte
    results_by_horizon = {}

    for horizon in horizons:
        print(f"\n{'─'*80}")
        print(f"📊 Horizonte: {horizon} velas ({horizon} minutos)")
        print(f"{'─'*80}")

        stats = []

        for trade in trades:
            entry_time = pd.to_datetime(trade["entry_time"], unit="ms", utc=True)
            entry_price = trade["entry_price"]
            position_side = trade["position_side"]

            try:
                idx = df.index.get_indexer([entry_time], method="nearest")[0]

                if idx == -1:
                    continue

                future_candles = df.iloc[idx : idx + horizon + 1]

                if len(future_candles) < 2:
                    continue

                highs = future_candles["high"].values
                lows = future_candles["low"].values

                if position_side == "LONG":
                    max_price = np.max(highs)
                    min_price = np.min(lows)
                    mfe = (max_price - entry_price) / entry_price
                    mae = (entry_price - min_price) / entry_price
                else:  # SHORT
                    max_price = np.max(highs)
                    min_price = np.min(lows)
                    mfe = (entry_price - min_price) / entry_price
                    mae = (max_price - entry_price) / entry_price

                stats.append(
                    {
                        "trade_id": trade["id"],
                        "side": position_side,
                        "mfe": mfe * 100,
                        "mae": mae * 100,
                        "mfe_mae_ratio": mfe / (mae + 1e-9),
                    }
                )

            except (KeyError, IndexError):
                continue

        if not stats:
            print("❌ No se pudieron analizar trades para este horizonte.")
            continue

        df_stats = pd.DataFrame(stats)

        # Calcular métricas
        avg_mfe = df_stats["mfe"].mean()
        avg_mae = df_stats["mae"].mean()
        mfe_mae_ratio = df_stats["mfe_mae_ratio"].mean()

        # Win rates teóricos para diferentes TP/SL
        tp_sl_configs = [
            (0.3, 0.3),
            (0.5, 0.5),
            (0.6, 0.6),
            (1.0, 1.0),
            (1.5, 1.5),
            (2.0, 2.0),
        ]

        print(f"\n📈 Métricas:")
        print(f"  MFE promedio: {avg_mfe:.4f}%")
        print(f"  MAE promedio: {avg_mae:.4f}%")
        print(f"  MFE/MAE Ratio: {mfe_mae_ratio:.4f}")

        print(f"\n🎯 Win Rates Teóricos por TP/SL:")
        print(f"  {'TP/SL':<12} {'WR Teórico':<15} {'Viable?':<10}")
        print(f"  {'-'*40}")

        for tp, sl in tp_sl_configs:
            wr_theoretical = (df_stats["mfe"] >= tp).mean() * 100
            viable = "✅ Sí" if wr_theoretical >= 50 else "❌ No"
            print(f"  {tp:.1f}% / {sl:.1f}%  {wr_theoretical:>6.2f}%        {viable}")

        # Encontrar TP/SL óptimo
        optimal_tp = avg_mfe * 0.8  # 80% del MFE promedio
        optimal_sl = avg_mae * 0.8  # 80% del MAE promedio
        optimal_wr = (df_stats["mfe"] >= optimal_tp).mean() * 100

        print(f"\n💡 TP/SL Óptimo Sugerido:")
        print(f"  TP: {optimal_tp:.3f}% (80% del MFE promedio)")
        print(f"  SL: {optimal_sl:.3f}% (80% del MAE promedio)")
        print(f"  Ratio: {optimal_tp/optimal_sl:.2f}:1")
        print(f"  WR Esperado: {optimal_wr:.2f}%")

        # Interpretación
        print(f"\n🔍 Interpretación:")
        if avg_mfe > avg_mae * 1.2:
            print(f"  ✅ Señales tienen EDGE POSITIVO en este horizonte")
            print(f"     (MFE {avg_mfe:.3f}% > MAE {avg_mae:.3f}%)")
        elif avg_mfe > avg_mae:
            print(f"  ⚠️ Señales tienen EDGE MARGINAL en este horizonte")
            print(f"     (MFE {avg_mfe:.3f}% ≈ MAE {avg_mae:.3f}%)")
        else:
            print(f"  ❌ Señales NO tienen edge en este horizonte")
            print(f"     (MFE {avg_mfe:.3f}% ≤ MAE {avg_mae:.3f}%)")

        # Guardar resultados
        results_by_horizon[horizon] = {
            "avg_mfe": avg_mfe,
            "avg_mae": avg_mae,
            "mfe_mae_ratio": mfe_mae_ratio,
            "optimal_tp": optimal_tp,
            "optimal_sl": optimal_sl,
            "optimal_wr": optimal_wr,
        }

    # Resumen comparativo
    print(f"\n{'='*80}")
    print(f"📊 RESUMEN COMPARATIVO")
    print(f"{'='*80}\n")

    print(f"{'Horizonte':<12} {'MFE%':<10} {'MAE%':<10} {'Ratio':<10} {'TP Óptimo':<12} {'WR Esperado':<12}")
    print(f"{'-'*80}")

    for horizon in horizons:
        if horizon in results_by_horizon:
            r = results_by_horizon[horizon]
            print(
                f"{horizon:>3} velas    {r['avg_mfe']:>6.3f}%   {r['avg_mae']:>6.3f}%   "
                f"{r['mfe_mae_ratio']:>6.2f}   {r['optimal_tp']:>6.3f}%      {r['optimal_wr']:>6.2f}%"
            )

    # Recomendación final
    print(f"\n{'='*80}")
    print(f"💡 RECOMENDACIÓN FINAL")
    print(f"{'='*80}\n")

    # Encontrar mejor horizonte
    best_horizon = None
    best_ratio = 0

    for horizon, r in results_by_horizon.items():
        if r["mfe_mae_ratio"] > best_ratio:
            best_ratio = r["mfe_mae_ratio"]
            best_horizon = horizon

    if best_horizon:
        r = results_by_horizon[best_horizon]
        print(f"🎯 Mejor horizonte: {best_horizon} velas ({best_horizon} minutos)")
        print(f"   MFE/MAE Ratio: {r['mfe_mae_ratio']:.2f}")
        print(f"   TP sugerido: {r['optimal_tp']:.3f}%")
        print(f"   SL sugerido: {r['optimal_sl']:.3f}%")
        print(f"   WR esperado: {r['optimal_wr']:.2f}%")

        if r["avg_mfe"] > r["avg_mae"] * 1.2:
            print(f"\n✅ Este horizonte muestra edge positivo - vale la pena optimizar aquí.")
        else:
            print(f"\n⚠️ Incluso en el mejor horizonte, el edge es marginal o negativo.")
            print(f"   Prioridad: Mejorar calidad de señales antes de optimizar TP/SL.")

    print(f"\n{'='*80}\n")


def main():
    if len(sys.argv) < 3:
        print("Uso: python analyze_mfe_mae_multi.py <data_csv> <backtest_json> [horizons]")
        print("\nEjemplo:")
        print("  python analyze_mfe_mae_multi.py data.csv backtest.json")
        print("  python analyze_mfe_mae_multi.py data.csv backtest.json 10,30,60,120,240")
        sys.exit(1)

    data_file = sys.argv[1]
    log_file = sys.argv[2]

    # Parse horizons si se proporcionan
    if len(sys.argv) >= 4:
        horizons = [int(h) for h in sys.argv[3].split(",")]
    else:
        horizons = [10, 30, 60, 120, 240]  # Default: 10min, 30min, 1h, 2h, 4h

    analyze_multi_horizon(data_file, log_file, horizons)


if __name__ == "__main__":
    main()
