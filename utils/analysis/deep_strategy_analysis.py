#!/usr/bin/env python3
"""
Deep Strategy Analysis — Diagnóstico completo de la estrategia LTA V6
Analiza señales, guardians, sensores tácticos y resultados para identificar problemas raíz.
"""

import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime

# ANSI Colors
CYAN = "\033[96m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def header(msg):
    line = "=" * 80
    return f"\n{BOLD}{CYAN}{line}\n  {msg}\n{line}{RESET}"


def analyze_signals(conn):
    """Analiza las señales generadas y su calidad."""
    print(header("1. ANÁLISIS DE SEÑALES GENERADAS"))

    signals = conn.execute(
        """
        SELECT timestamp, symbol, side, price, setup_type, metadata
        FROM signals
        ORDER BY timestamp
    """
    ).fetchall()

    print(f"Total señales: {len(signals)}")

    # Por setup type
    by_setup = defaultdict(int)
    for sig in signals:
        by_setup[sig[4]] += 1

    print(f"\nPor Setup Type:")
    for setup, count in by_setup.items():
        print(f"  {setup}: {count}")

    # Por side
    longs = sum(1 for s in signals if s[2] == "LONG")
    shorts = sum(1 for s in signals if s[2] == "SHORT")
    print(f"\nPor Side:")
    print(f"  LONG: {longs} ({longs/len(signals)*100:.1f}%)")
    print(f"  SHORT: {shorts} ({shorts/len(signals)*100:.1f}%)")

    return signals


def analyze_guardian_rejections(conn):
    """Analiza qué guardians están rechazando más señales."""
    print(header("2. ANÁLISIS DE GUARDIANS (Rechazos)"))

    traces = conn.execute(
        """
        SELECT gate, reason, COUNT(*) as count
        FROM decision_traces
        WHERE status = 'REJECT'
        GROUP BY gate, reason
        ORDER BY count DESC
    """
    ).fetchall()

    if not traces:
        print("⚠️ No hay decision traces de rechazos")
        return

    print(f"{'Guardian':<30} {'Razón':<50} {'Count':<10}")
    print("-" * 90)

    total_rejects = sum(t[2] for t in traces)
    for gate, reason, count in traces[:20]:  # Top 20
        pct = count / total_rejects * 100
        print(f"{gate:<30} {reason:<50} {count:<10} ({pct:.1f}%)")

    print(f"\nTotal rechazos: {total_rejects}")


def analyze_guardian_passes(conn):
    """Analiza qué guardians están pasando señales."""
    print(header("3. ANÁLISIS DE GUARDIANS (Aprobaciones)"))

    traces = conn.execute(
        """
        SELECT gate, reason, COUNT(*) as count
        FROM decision_traces
        WHERE status = 'PASS'
        GROUP BY gate, reason
        ORDER BY count DESC
    """
    ).fetchall()

    if not traces:
        print("⚠️ No hay decision traces de aprobaciones")
        return

    print(f"{'Guardian':<30} {'Razón':<50} {'Count':<10}")
    print("-" * 90)

    for gate, reason, count in traces[:15]:  # Top 15
        print(f"{gate:<30} {reason:<50} {count:<10}")


def analyze_mfe_mae_by_condition(conn, signals):
    """Analiza MFE/MAE por condición de mercado usando timestamps."""
    print(header("4. ANÁLISIS MFE/MAE POR CONDICIÓN"))

    # Timestamp ranges para cada condición
    conditions = {
        "RANGE": (1723593600, 1723852800),  # Aug 14-16
        "BEAR": (1725494400, 1725753600),  # Sep 05-07
        "BULL": (1728777600, 1729036800),  # Oct 13-15
    }

    for cond_name, (start_ts, end_ts) in conditions.items():
        cond_signals = [s for s in signals if start_ts <= s[0] <= end_ts]

        if not cond_signals:
            print(f"\n{cond_name}: No signals")
            continue

        print(f"\n{cond_name} (n={len(cond_signals)}):")

        # Calcular MFE/MAE para cada señal
        mfes = []
        maes = []
        wins = 0
        losses = 0

        for sig in cond_signals:
            ts, sym, side, price = sig[0], sig[1], sig[2], sig[3]

            # Get price trajectory
            prices = conn.execute(
                """
                SELECT price FROM price_samples
                WHERE symbol = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            """,
                (sym, ts, ts + 900),
            ).fetchall()

            if not prices:
                continue

            prices_list = [p[0] for p in prices]

            if side == "LONG":
                mfe = max((p - price) / price * 100 for p in prices_list)
                mae = max((price - p) / price * 100 for p in prices_list)
            else:  # SHORT
                mfe = max((price - p) / price * 100 for p in prices_list)
                mae = max((p - price) / price * 100 for p in prices_list)

            mfes.append(mfe)
            maes.append(mae)

            # Check if hit TP or SL first (0.3%/0.3%)
            for p in prices_list:
                pnl = (p - price) / price * 100 if side == "LONG" else (price - p) / price * 100
                if pnl >= 0.3:
                    wins += 1
                    break
                if pnl <= -0.3:
                    losses += 1
                    break

        if mfes:
            avg_mfe = statistics.mean(mfes)
            avg_mae = statistics.mean(maes)
            ratio = avg_mfe / (avg_mae + 1e-9)
            decided = wins + losses
            wr = wins / decided * 100 if decided > 0 else 0
            expectancy = (wr / 100) * avg_mfe - ((100 - wr) / 100) * avg_mae

            print(f"  Avg MFE: {avg_mfe:.3f}%")
            print(f"  Avg MAE: {avg_mae:.3f}%")
            print(f"  Ratio: {ratio:.2f}")
            print(f"  WR (0.3%/0.3%): {wr:.1f}% ({wins}W / {losses}L / {len(cond_signals)-decided}T)")
            print(f"  Expectancy: {expectancy:+.4f}%")

            if expectancy > 0.36:
                verdict = f"{GREEN}CERTIFIED{RESET}"
            elif expectancy > 0.12:
                verdict = f"{YELLOW}WATCH{RESET}"
            else:
                verdict = f"{RED}FAILED{RESET}"
            print(f"  Veredicto: {verdict}")


def analyze_tactical_sensors(conn):
    """Analiza qué sensores tácticos están generando las señales."""
    print(header("5. ANÁLISIS DE SENSORES TÁCTICOS"))

    # Extraer sensor info del metadata de signals
    signals = conn.execute("SELECT metadata FROM signals").fetchall()

    sensor_counts = defaultdict(int)
    for sig in signals:
        metadata = sig[0]
        # El metadata contiene info del sensor que disparó
        if "sensor" in metadata.lower():
            # Parsear el metadata (es un string)
            if "FootprintVolumeExhaustion" in metadata:
                sensor_counts["FootprintVolumeExhaustion"] += 1
            elif "FootprintTrappedTraders" in metadata:
                sensor_counts["FootprintTrappedTraders"] += 1
            elif "FootprintDeltaPoCShift" in metadata:
                sensor_counts["FootprintDeltaPoCShift"] += 1
            elif "FootprintDeltaDivergence" in metadata:
                sensor_counts["FootprintDeltaDivergence"] += 1

    if sensor_counts:
        print(f"{'Sensor':<40} {'Count':<10}")
        print("-" * 50)
        for sensor, count in sorted(sensor_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"{sensor:<40} {count:<10}")
    else:
        print("⚠️ No se pudo extraer info de sensores del metadata")


def analyze_timing_distribution(conn, signals):
    """Analiza la distribución temporal de las señales."""
    print(header("6. DISTRIBUCIÓN TEMPORAL DE SEÑALES"))

    # Por hora del día
    by_hour = defaultdict(int)
    for sig in signals:
        ts = sig[0]
        dt = datetime.utcfromtimestamp(ts)
        by_hour[dt.hour] += 1

    print("\nSeñales por hora UTC:")
    for hour in sorted(by_hour.keys()):
        count = by_hour[hour]
        bar = "█" * (count // 2)
        print(f"  {hour:02d}:00 | {bar} {count}")


def analyze_price_levels(conn, signals):
    """Analiza si las señales están realmente en los niveles estructurales."""
    print(header("7. ANÁLISIS DE NIVELES ESTRUCTURALES"))

    # Analizar distancia promedio a VAH/VAL
    distances = []

    for sig in signals:
        metadata = str(sig[5])
        # Extraer distancia del metadata si está disponible
        if "dist:" in metadata or "distance:" in metadata:
            # Parsear distancia
            try:
                if "dist:" in metadata:
                    dist_str = metadata.split("dist:")[1].split("%")[0].strip()
                    dist = float(dist_str)
                    distances.append(abs(dist))
            except (ValueError, IndexError):
                pass

    if distances:
        avg_dist = statistics.mean(distances)
        max_dist = max(distances)
        min_dist = min(distances)

        print(f"Distancia a nivel estructural:")
        print(f"  Promedio: {avg_dist:.4f}%")
        print(f"  Mínima: {min_dist:.4f}%")
        print(f"  Máxima: {max_dist:.4f}%")
        print(f"  Threshold configurado: 0.20%")

        if avg_dist > 0.20:
            print(f"  {RED}⚠️ Señales están lejos de los niveles estructurales{RESET}")
    else:
        print("⚠️ No se pudo extraer info de distancia del metadata")


def main():
    conn = sqlite3.connect("data/historian.db")

    print(header("DEEP STRATEGY ANALYSIS — LTA V6"))
    print(f"Database: data/historian.db")
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Análisis de señales
    signals = analyze_signals(conn)

    if not signals:
        print(f"\n{RED}❌ No hay señales en la base de datos{RESET}")
        return

    # 2. Análisis de guardians (rechazos)
    analyze_guardian_rejections(conn)

    # 3. Análisis de guardians (aprobaciones)
    analyze_guardian_passes(conn)

    # 4. MFE/MAE por condición
    analyze_mfe_mae_by_condition(conn, signals)

    # 5. Sensores tácticos
    analyze_tactical_sensors(conn)

    # 6. Distribución temporal
    analyze_timing_distribution(conn, signals)

    # 7. Niveles estructurales
    analyze_price_levels(conn, signals)

    print(header("ANÁLISIS COMPLETADO"))

    conn.close()


if __name__ == "__main__":
    main()
