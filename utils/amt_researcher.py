import json
import sqlite3
import statistics


def calculate_mfe(conn, symbol, side, entry_price, start_ts, end_ts):
    ps = conn.execute(
        "SELECT price FROM price_samples WHERE symbol=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
        (symbol, start_ts, end_ts),
    ).fetchall()

    if not ps:
        return 0.0

    max_mfe = 0.0
    for (p,) in ps:
        m = (p - entry_price) / entry_price * 100.0
        if side == "SHORT":
            m = -m
        if m > max_mfe:
            max_mfe = m

    return max_mfe


def run_research():
    print("🔬 Iniciando Investigación de Geometría AMT (Zero-Interference)...\n")
    conn = sqlite3.connect("data/historian.db")
    signals = conn.execute("SELECT timestamp, symbol, side, price, metadata FROM signals ORDER BY timestamp").fetchall()

    if not signals:
        print("❌ No hay señales en historian.db")
        return

    results = []

    for ts, sym, side, price, meta_str in signals:
        try:
            meta = json.loads(meta_str)
        except (json.JSONDecodeError, TypeError):
            continue

        poc_p = meta.get("poc_price", 0.0)
        vah_p = meta.get("vah_price", 0.0)
        val_p = meta.get("val_price", 0.0)
        va_w_abs = meta.get("va_width", 0.0)

        if va_w_abs <= 0.0 or price <= 0.0:
            continue

        va_w_pct = (va_w_abs / price) * 100.0

        # Calculate distance to POC
        dist_to_poc_pct = (abs(price - poc_p) / price) * 100.0

        # Calculate distance to opposite boundary (if LONG, aim for VAH. If SHORT, aim for VAL)
        opp_boundary = vah_p if side == "LONG" else val_p
        dist_to_opp_pct = (abs(opp_boundary - price) / price) * 100.0

        mfe_pct = calculate_mfe(conn, sym, side, price, ts, ts + 3600)

        # Only consider trades where market actually moved (MFE > 0.1%) to avoid noise
        if mfe_pct > 0.1:
            ratio_mfe_to_vaw = mfe_pct / va_w_pct if va_w_pct > 0 else 0
            ratio_mfe_to_poc = mfe_pct / dist_to_poc_pct if dist_to_poc_pct > 0 else 0
            ratio_mfe_to_opp = mfe_pct / dist_to_opp_pct if dist_to_opp_pct > 0 else 0

            results.append(
                {
                    "mfe": mfe_pct,
                    "va_w": va_w_pct,
                    "ratio_vaw": ratio_mfe_to_vaw,
                    "ratio_poc": ratio_mfe_to_poc,
                    "ratio_opp": ratio_mfe_to_opp,
                }
            )

    if not results:
        print("⚠️ No hay suficientes datos limpios para correlacionar.")
        return

    avg_mfe = statistics.mean([r["mfe"] for r in results])
    avg_vaw = statistics.mean([r["va_w"] for r in results])

    median_ratio_vaw = statistics.median([r["ratio_vaw"] for r in results])
    median_ratio_poc = statistics.median([r["ratio_poc"] for r in results])
    median_ratio_opp = statistics.median([r["ratio_opp"] for r in results])

    print("📊 RESULTADOS DEL CRUCE GEOMÉTRICO (MFE vs Estructura)")
    print("-" * 50)
    print(f"Total Señales Analizadas (MFE > 0.1%): {len(results)}")
    print(f"MFE Promedio de la muestra:            {avg_mfe:.3f}%")
    print(f"Ancho Promedio del Área de Valor:      {avg_vaw:.3f}%")
    print("-" * 50)
    print("🎯 DESCUBRIMIENTO DE MULTIPLICADORES (Mediana):")
    print(f"MFE vs Ancho de Valor (VAW):           {median_ratio_vaw:.2f}x")
    print(f"MFE vs Distancia al POC:               {median_ratio_poc:.2f}x")
    print(f"MFE vs Límite Opuesto (VAH/VAL):       {median_ratio_opp:.2f}x")
    print("-" * 50)

    print("\n💡 INTERPRETACIÓN:")
    if median_ratio_vaw >= 1.0 and median_ratio_vaw <= 2.0:
        print("El precio tiende a expandirse una distancia muy correlacionada al ancho del Área de Valor.")
    else:
        print("La correlación con el ancho total del área es dispersa.")

    print(
        f"\n=> Si usáramos VAW * {median_ratio_vaw:.1f} como Target Dinámico, capturaríamos la mayoría del MFE estructural.\n"
    )


if __name__ == "__main__":
    run_research()
