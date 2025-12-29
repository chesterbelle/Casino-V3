"""
Herramienta rápida para validar la conexión con ASTERDEx.

Uso:
    python3 -m utils.test_aster_connection --symbol BTCUSDT --interval 1m
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Dict

from utils.aster_env_loader import load_aster_credentials
from utils.asterdex_client import AsterDexAPIError, AsterDexClient


def pretty(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, indent=2, sort_keys=True)


def run_probe(symbol: str, interval: str, limit: int) -> Dict[str, Any]:
    creds = load_aster_credentials(test_connection=True)
    client = AsterDexClient(
        api_key=creds["api_key"],
        api_secret=creds["api_secret"],
        base_url=creds["base_url"],
    )

    result: Dict[str, Any] = {"creds_connected": creds["connected"]}
    result["server_time"] = client.get_server_time()
    result["exchange_info"] = client.get_exchange_info(symbol=symbol)
    result["mark_price"] = client.get_mark_price(symbol=symbol)
    result["sample_klines"] = client.get_klines(symbol, interval, limit=limit)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida credenciales y endpoints de ASTERDEx")
    parser.add_argument("--symbol", default=None, help="Símbolo del contrato (ej. BTCUSDT)")
    parser.add_argument("--interval", default=None, help="Intervalo de velas (ej. 1m, 5m)")
    parser.add_argument("--limit", type=int, default=5, help="Cantidad de velas a consultar")
    args = parser.parse_args()

    from config import (  # evita importar arriba
        ASTER_DEFAULT_INTERVAL,
        ASTER_DEFAULT_SYMBOL,
    )

    symbol = (args.symbol or ASTER_DEFAULT_SYMBOL).upper()
    interval = args.interval or ASTER_DEFAULT_INTERVAL

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    try:
        probe = run_probe(symbol, interval, args.limit)
    except AsterDexAPIError as exc:
        logging.error("Error de API ASTER: %s", exc)
        raise SystemExit(1) from exc
    except Exception as exc:
        logging.exception("Fallo inesperado durante la prueba ASTER.")
        raise SystemExit(1) from exc

    logging.info("Conexión ASTER exitosa. Resumen:")
    for key, value in probe.items():
        logging.info("%s => %s", key, pretty(value)[:1000])


if __name__ == "__main__":
    main()
