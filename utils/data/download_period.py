#!/usr/bin/env python3
"""
Descarga de Datos por Periodo (Chunked)
---------------------------------------
Descarga velas históricas para un rango de fechas específico, dividiéndolo
automáticamente en archivos de máximo 30 días para facilitar el entrenamiento.

Los archivos generados tendrán el sufijo '_training' y se guardarán en data/raw.

Uso:
    python3 utils/data/download_period.py --symbol BTCUSDT --start 2022-01-01 --end 2022-12-31
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List

# Asegurar que el root del proyecto está en sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Importar utilidades existentes
from utils.data.download_kline_dataset import fetch_klines, interval_to_ms, save_csv

# Configurar logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("DownloadPeriod")


def parse_date(date_str: str) -> datetime:
    """Parsea fecha en formato YYYY-MM-DD."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.error(f"❌ Formato de fecha inválido: {date_str}. Use YYYY-MM-DD")
        sys.exit(1)


def download_chunk(symbol: str, interval: str, start_dt: datetime, end_dt: datetime) -> bool:
    """Descarga un chunk específico y lo guarda."""
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    interval_ms = interval_to_ms(interval)

    klines: List[List[Any]] = []
    current = start_ms

    logger.info(f"⬇️  Descargando chunk: {start_dt.date()} -> {end_dt.date()}")

    while current < end_ms:
        # Binance API limit is usually 1000 or 1500
        batch = fetch_klines(symbol, interval, start_time=current, limit=1500)
        if not batch:
            break

        # Filtrar velas que se pasen del end_ms (por si acaso la API devuelve de más)
        batch = [k for k in batch if int(k[0]) < end_ms]
        if not batch:
            break

        klines.extend(batch)
        last_open = int(batch[-1][0])
        next_start = last_open + interval_ms

        if next_start <= current:  # Evitar bucles infinitos si la API devuelve lo mismo
            current += interval_ms
        else:
            current = next_start

    if not klines:
        logger.warning(f"⚠️  No se encontraron datos para el periodo {start_dt.date()} -> {end_dt.date()}")
        return False

    # Generar tag con fechas y sufijo training
    tag = f"{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}_training"

    # Guardar archivo
    out_path = save_csv(symbol, interval, klines, tag=tag)
    logger.info(f"✅ Guardado: {Path(out_path).name} ({len(klines)} velas)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Descarga datos históricos por periodo.")
    parser.add_argument("--symbol", required=True, help="Símbolo (ej. BTCUSDT)")
    parser.add_argument("--start", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--interval", default="1m", help="Intervalo (default: 1m)")
    parser.add_argument("--chunk-days", type=int, default=30, help="Tamaño del chunk en días (default: 30)")

    args = parser.parse_args()

    symbol = args.symbol.upper()
    if not symbol.endswith("USDT") and not symbol.endswith("USD"):  # Simple check
        symbol = f"{symbol}USDT"

    start_date = parse_date(args.start)
    end_date = parse_date(args.end)

    # Ajustar end_date para incluir el último día completo (hasta las 23:59:59)
    # Si el usuario pone 2022-01-31, queremos que incluya todo el 31.
    # parse_date devuelve 00:00:00.
    # Así que sumamos 1 día al end_date para que el loop funcione como [start, end)
    end_date = end_date + timedelta(days=1)

    if start_date >= end_date:
        logger.error("❌ La fecha de inicio debe ser anterior a la fecha de fin.")
        return 1

    logger.info(f"🚀 Iniciando descarga masiva para {symbol}")
    logger.info(f"📅 Periodo total: {start_date.date()} -> {args.end}")
    logger.info(f"⏱️  Intervalo: {args.interval}")
    logger.info(f"📦 Chunk size: {args.chunk_days} días")
    logger.info("-" * 50)

    current_start = start_date
    total_chunks = 0
    success_chunks = 0

    while current_start < end_date:
        current_end = min(current_start + timedelta(days=args.chunk_days), end_date)

        if download_chunk(symbol, args.interval, current_start, current_end):
            success_chunks += 1

        total_chunks += 1
        current_start = current_end

    logger.info("-" * 50)
    logger.info(f"🏁 Proceso finalizado. Chunks exitosos: {success_chunks}/{total_chunks}")

    return 0 if success_chunks > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
