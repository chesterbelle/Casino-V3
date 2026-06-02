#!/usr/bin/env python3
"""
Price History Analyzer — Decide qué meses descargar
----------------------------------------------------
Analiza precios históricos de Binance Futures para clasificar meses
por condición de mercado (TREND_UP, TREND_DOWN, BALANCE) y recomendar
datasets para backtesting.

Uso:
    python utils/data/price_history_analyzer.py --symbol SOL --months 24
    python utils/data/price_history_analyzer.py --symbol XRP --recommend
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

API_URL = "https://fapi.binance.com/fapi/v1/klines"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def fetch_klines(
    symbol: str,
    interval: str = "1d",
    days: int = 730,
    limit: int = 1000,
) -> List[List[Any]]:
    """Fetch velas desde Binance Futures API pública."""
    symbol = symbol.upper()
    if not symbol.endswith("USDT"):
        symbol = f"{symbol}USDT"

    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(days=days)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    all_klines: List[List[Any]] = []
    current = start_ms

    while current < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current,
            "limit": limit,
        }
        try:
            resp = requests.get(API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"⚠️ API error: {e}")
            break

        if not data or not isinstance(data, list):
            break

        all_klines.extend(data)
        last_open = int(data[-1][0])
        current = last_open + 86400000  # +1 day in ms

        if len(data) < limit:
            break

    return [k for k in all_klines if int(k[0]) >= start_ms]


def get_month_key(timestamp_ms: int) -> str:
    """Extrae YYYY-MM de un timestamp en ms."""
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m")


def classify_month(klines: List[List[Any]]) -> str:
    """Clasifica un grupo de velas diarias como TREND_UP, TREND_DOWN, o BALANCE."""
    if len(klines) < 5:
        return "INSUFFICIENT"

    opens = [float(k[1]) for k in klines]
    closes = [float(k[4]) for k in klines]

    first_open = opens[0]
    last_close = closes[-1]

    if first_open == 0:
        return "INSUFFICIENT"

    change_pct = ((last_close - first_open) / first_open) * 100

    # Contar días directionales
    up_days = sum(1 for o, c in zip(opens, closes) if c > o)
    down_days = sum(1 for o, c in zip(opens, closes) if c < o)
    total_days = len(klines)

    direction_ratio = max(up_days, down_days) / total_days if total_days > 0 else 0

    # Clasificación
    if abs(change_pct) < 5:
        return "BALANCE"
    elif change_pct > 10 and direction_ratio > 0.55:
        return "TREND_UP"
    elif change_pct < -10 and direction_ratio > 0.55:
        return "TREND_DOWN"
    elif change_pct > 5:
        return "TREND_UP"
    elif change_pct < -5:
        return "TREND_DOWN"
    else:
        return "BALANCE"


def analyze_symbol(symbol: str, months: int = 24) -> Dict[str, Dict]:
    """Analiza cada mes y retorna clasificación."""
    days = months * 31  # Approximar
    klines = fetch_klines(symbol, interval="1d", days=days)

    if not klines:
        logger.error(f"❌ No se obtuvieron datos para {symbol}")
        return {}

    # Agrupar por mes
    by_month: Dict[str, List[List[Any]]] = {}
    for k in klines:
        month = get_month_key(int(k[0]))
        if month not in by_month:
            by_month[month] = []
        by_month[month].append(k)

    results = {}
    for month, month_klines in sorted(by_month.items()):
        classification = classify_month(month_klines)
        opens = [float(k[1]) for k in month_klines]
        closes = [float(k[4]) for k in month_klines]
        change_pct = ((closes[-1] - opens[0]) / opens[0]) * 100 if opens[0] > 0 else 0

        results[month] = {
            "classification": classification,
            "change_pct": round(change_pct, 2),
            "days": len(month_klines),
        }

    return results


def recommend_datasets(
    symbol: str,
    months: int = 24,
    per_condition: int = 2,
) -> List[str]:
    """Recomienda fechas (YYYY-MM-01) con condiciones variadas."""
    analysis = analyze_symbol(symbol, months)

    if not analysis:
        return []

    # Agrupar por condición
    by_condition: Dict[str, List[str]] = {
        "TREND_UP": [],
        "TREND_DOWN": [],
        "BALANCE": [],
    }

    for month, info in analysis.items():
        cond = info["classification"]
        if cond in by_condition:
            # Preferir meses con mayor variación absoluta
            by_condition[cond].append((month, abs(info["change_pct"])))

    # Ordenar por variación (mayor primero) y tomar top N
    recommendations = []
    for cond in ["TREND_UP", "TREND_DOWN", "BALANCE"]:
        candidates = sorted(by_condition[cond], key=lambda x: x[1], reverse=True)
        for month, _ in candidates[:per_condition]:
            recommendations.append(f"{month}-01")

    return sorted(recommendations)


def print_analysis(symbol: str, results: Dict[str, Dict]) -> None:
    """Imprime análisis formateado."""
    print(f"\n{'='*50}")
    print(f"  {symbol.upper()} - Análisis de Condiciones por Mes")
    print(f"{'='*50}")

    for month, info in sorted(results.items()):
        cond = info["classification"]
        change = info["change_pct"]
        icon = {"TREND_UP": "🟢", "TREND_DOWN": "🔴", "BALANCE": "⚪"}.get(cond, "❓")
        print(f"  {icon} {month}: {cond:12s} ({change:+.1f}%)")

    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="Analiza precios históricos para decidir qué meses descargar.")
    parser.add_argument("--symbol", required=True, help="Símbolo (ej: SOL, XRP, DOGE)")
    parser.add_argument("--months", type=int, default=24, help="Meses hacia atrás a analizar (default: 24)")
    parser.add_argument("--recommend", action="store_true", help="Recomendar 6 fechas con condiciones variadas")
    parser.add_argument("--per-condition", type=int, default=2, help="Datasets por condición (default: 2)")

    args = parser.parse_args()
    symbol = args.symbol.upper()

    if args.recommend:
        recs = recommend_datasets(symbol, args.months, args.per_condition)
        if recs:
            print(f"\n📅 Recomendación para {symbol}:")
            for r in recs:
                print(f"  {r}")
            print(f"\nTotal: {len(recs)} datasets sugeridos")
        else:
            print(f"❌ No se encontraron recomendaciones para {symbol}")
    else:
        results = analyze_symbol(symbol, args.months)
        if results:
            print_analysis(symbol, results)
        else:
            print(f"❌ No se pudieron analizar datos para {symbol}")


if __name__ == "__main__":
    main()
