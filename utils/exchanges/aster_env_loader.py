"""
====================================================
ASTER Env Loader — gestor de credenciales paper/live
====================================================

Rol:
----
• Carga claves y endpoints para la API de ASTERDEx desde `.env` o `config.py`.
• Valida conectividad básica (opcional) llamando a `/fapi/v1/time`.
• Devuelve un diccionario estándar reutilizable por mesas realtime.

Variables esperadas:
--------------------
ASTER_API_KEY, ASTER_API_SECRET, ASTER_BASE_URL, ASTER_WS_URL

Uso rápido:
-----------
from utils.aster_env_loader import load_aster_credentials

creds = load_aster_credentials(test_connection=True)
if creds["connected"]:
    print("Listo para paper trading ASTER.")
"""

from __future__ import annotations

import logging
import os
from typing import Dict

from dotenv import load_dotenv

from utils.asterdex_client import DEFAULT_BASE_URL, AsterDexClient


def load_aster_credentials(test_connection: bool = False) -> Dict[str, str]:
    """
    Carga credenciales/endpoints y, si se solicita, prueba la conexión.

    Retorna:
    --------
    {
        "api_key": str | None,
        "api_secret": str | None,
        "base_url": str,
        "ws_url": str | None,
        "connected": bool
    }
    """

    logger = logging.getLogger("AsterEnvLoader")

    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info("Archivo .env encontrado en la raíz del proyecto: %s", env_path)
    else:
        logger.warning("No se encontró archivo .env en la raíz del proyecto.")

    import config  # noqa: WPS433  # carga perezosa para tomar defaults del usuario

    api_key = os.getenv("ASTER_API_KEY") or getattr(config, "ASTER_API_KEY", None)
    api_secret = os.getenv("ASTER_API_SECRET") or getattr(config, "ASTER_API_SECRET", None)
    base_url = (os.getenv("ASTER_BASE_URL") or getattr(config, "ASTER_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
    ws_url = os.getenv("ASTER_WS_URL") or getattr(config, "ASTER_WS_URL", None)

    connected = False
    if not api_key or not api_secret:
        logger.warning("Claves ASTER incompletas. Funcionalidad firmada deshabilitada.")
    elif test_connection:
        try:
            client = AsterDexClient(
                api_key=api_key,
                api_secret=api_secret,
                base_url=base_url,
                recv_window=getattr(config, "ASTER_RECV_WINDOW", 5000),
            )
            client.get_server_time()
            connected = True
            logger.info("API ASTER responde correctamente (server time).")
        except Exception as exc:
            logger.error("Error validando credenciales ASTER: %s", exc)
    else:
        logger.info("Claves ASTER cargadas (sin test).")

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "base_url": base_url,
        "ws_url": ws_url,
        "connected": connected,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = load_aster_credentials(test_connection=True)
    logger = logging.getLogger("AsterEnvLoader")
    logger.info("\nResultado ASTER:")
    for key, value in result.items():
        logger.info(f"  {key}: {value}")
