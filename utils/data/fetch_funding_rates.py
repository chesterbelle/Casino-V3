#!/usr/bin/env python3
"""
Descarga tasas de funding históricas desde la API de Binance Futures
y las guarda en tables/data/funding_rates/<SYMBOL>.csv.
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "tables",
    "data",
    "funding_rates",
)

API_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def fetch_funding(
    symbol: str, limit: int = 1000, start_time: int | None = None, end_time: int | None = None
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"symbol": symbol.upper(), "limit": limit}
    if start_time is not None:
        params["startTime"] = start_time
    if end_time is not None:
        params["endTime"] = end_time

    response = requests.get(API_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Respuesta inesperada de Binance: {data}")
    return data


def save_csv(symbol: str, rows: List[Dict[str, Any]]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{symbol.upper()}.csv")

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["funding_time", "funding_time_ms", "funding_rate", "mark_price"])
        for row in rows:
            funding_time_ms = int(row["fundingTime"])
            funding_time_iso = datetime.fromtimestamp(funding_time_ms / 1000, tz=timezone.utc).isoformat()
            funding_rate = row.get("fundingRate", "0")
            mark_price = row.get("markPrice", "")
            writer.writerow([funding_time_iso, funding_time_ms, funding_rate, mark_price])

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga datos de funding de Binance Futures")
    parser.add_argument("--symbol", default="LTCUSDT", help="Símbolo Futures (ej. BTCUSDT, LTCUSDT)")
    parser.add_argument(
        "--limit", type=int, default=1000, help="Cantidad de registros a descargar (máximo 1000 por llamada)"
    )
    parser.add_argument("--start", type=int, default=None, help="Timestamp inicial en ms (opcional)")
    parser.add_argument("--end", type=int, default=None, help="Timestamp final en ms (opcional)")
    args = parser.parse_args()

    rows = fetch_funding(args.symbol, limit=args.limit, start_time=args.start, end_time=args.end)
    out_path = save_csv(args.symbol, rows)
    print(f"Funding guardado en: {out_path} ({len(rows)} registros)")


if __name__ == "__main__":
    main()
