#!/usr/bin/env python3
"""
Descarga datos históricos de velas desde la API de Binance Futures
y los guarda en tables/data/raw/<SYMBOL>_<INTERVAL>_<TAG>.csv
para usarlos en los backtests sin abrir main.py.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


import requests

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "raw",
)

API_URL = "https://fapi.binance.com/fapi/v1/continuousKlines"


def interval_to_ms(interval: str) -> int:
    unit_multipliers = {
        "ms": 1,
        "s": 1000,
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
    }
    interval = interval.strip().lower()
    if interval.endswith("mo"):
        value = int(interval[:-2])
        return value * 30 * 24 * 60 * 60 * 1000
    value_part = "".join(ch for ch in interval if ch.isdigit())
    unit_part = interval[len(value_part) :]
    if not value_part or unit_part not in unit_multipliers:
        raise ValueError(f"Intervalo inválido: {interval}")
    value = int(value_part)
    return value * unit_multipliers[unit_part]


def fetch_klines(
    symbol: str,
    interval: str,
    start_time: Optional[int] = None,
    limit: int = 1500,
    contract: str = "PERPETUAL",
) -> List[List[Any]]:
    params: Dict[str, Any] = {
        "pair": symbol.upper(),
        "contractType": contract.upper(),
        "interval": interval,
        "limit": limit,
    }
    if start_time is not None:
        params["startTime"] = start_time
    response = requests.get(API_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Respuesta inesperada de Binance: {data}")
    return data


def save_csv(symbol: str, interval: str, rows: List[List[Any]], tag: str | None = None) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    filename = f"{symbol.upper()}_{interval}_{suffix or 'dataset'}.csv"
    out_path = os.path.join(OUTPUT_DIR, filename)

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for row in rows:
            # Estructura de continuousKlines:
            # [openTime, open, high, low, close, volume, closeTime, ...]
            open_time = int(row[0])
            open_time_iso = datetime.fromtimestamp(open_time / 1000, tz=timezone.utc).isoformat()
            writer.writerow(
                [
                    open_time_iso,
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                ]
            )

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga dataset de velas de Binance Futures.")
    parser.add_argument("--symbol", default=None, help="Símbolo base (ej. BTC, LTC, ADA) o par completo (BTCUSDT)")
    parser.add_argument("--interval", default=None, help="Intervalo (ej. 1m, 5m, 15m, 1h, 4h, 1d)")
    parser.add_argument("--days", type=int, default=None, help="Cantidad de días hacia atrás a descargar (desde hoy)")
    parser.add_argument("--tag", default=None, help="Etiqueta opcional para el nombre del archivo")
    args = parser.parse_args()

    if args.symbol:
        symbol_input = args.symbol.strip()
    else:
        try:
            symbol_input = input("Ingrese símbolo (ej. ADA o ADAUSDT) [LTC]: ").strip()
        except EOFError:
            symbol_input = ""
        if not symbol_input:
            symbol_input = "LTC"
    symbol_input = symbol_input.upper()
    if not symbol_input.endswith("USDT"):
        symbol = f"{symbol_input}USDT"
    else:
        symbol = symbol_input

    if args.interval:
        interval = args.interval
    else:
        try:
            interval = input("Intervalo (ej. 1m, 5m, 15m) [15m]: ").strip()
            interval = interval or "15m"
        except EOFError:
            interval = "15m"
    days = args.days
    if days is None:
        try:
            days_str = input("Ingrese número de días a descargar (ej. 30): ").strip()
        except EOFError:
            days_str = ""
        try:
            days = int(days_str)
        except ValueError:
            days = 30
    days = max(1, days)

    interval_ms = interval_to_ms(interval)
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(days=days)).timestamp() * 1000)

    klines: List[List[Any]] = []
    current = start_ms
    logger.info(f"Descargando {symbol} {interval} de los últimos {days} días...")
    while current < end_ms:
        batch = fetch_klines(symbol, interval, start_time=current, limit=1500)
        if not batch:
            break
        klines.extend(batch)
        last_open = int(batch[-1][0])
        next_start = last_open + interval_ms
        if next_start <= current:
            break
        current = next_start
        if len(batch) < 1500:
            break

    klines = [k for k in klines if int(k[0]) >= start_ms and int(k[0]) <= end_ms]
    if not klines:
        logger.error("No se descargaron velas. Verifica los parámetros.")
        return

    tag = args.tag or f"{days}d"
    out_path = save_csv(symbol, interval, klines, tag=tag)
    logger.info(f"Dataset guardado en: {out_path} ({len(klines)} velas)")


if __name__ == "__main__":
    main()
