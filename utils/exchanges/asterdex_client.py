"""
====================================================
ASTERDEx Client — REST helper for Casino V2
====================================================

Rol:
----
• Firma y envía peticiones contra la API de futuros de ASTERDEx.
• Simplifica endpoints comunes para paper trading (server time, klines, órdenes).
• Evita depender de SDKs externos (reusa requests con HMAC SHA256).

Uso rápido:
-----------
from utils.asterdex_client import AsterDexClient

client = AsterDexClient(api_key="...", api_secret="...")
time_info = client.get_server_time()
order = client.place_order(symbol="BTCUSDT", side="BUY", type="MARKET", quantity=0.01)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, Mapping, Optional

import requests

DEFAULT_BASE_URL = "https://fapi.asterdex.com"


class AsterDexAPIError(RuntimeError):
    """Error levantado cuando ASTERDEx devuelve un código inesperado."""

    def __init__(self, status_code: int, payload: Any):
        message = f"ASTERDEx API error (status={status_code}): {payload}"
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AsterDexClient:
    """Cliente ligero para la API REST de Aster (futuros)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        recv_window: int = 5000,
        session: Optional[requests.Session] = None,
    ) -> None:
        import config  # carga perezosa para evitar ciclos al importar utilidades

        self.logger = logging.getLogger("AsterDexClient")
        self.api_key = api_key or os.getenv("ASTER_API_KEY") or getattr(config, "ASTER_API_KEY", None)
        self.api_secret = api_secret or os.getenv("ASTER_API_SECRET") or getattr(config, "ASTER_API_SECRET", None)
        self.base_url = (
            base_url or os.getenv("ASTER_BASE_URL") or getattr(config, "ASTER_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.recv_window = recv_window or getattr(config, "ASTER_RECV_WINDOW", 5000)
        self.session = session or requests.Session()
        self._time_offset_ms = 0
        self._last_time_sync = 0.0

        if not self.base_url.startswith("http"):
            raise ValueError(f"Base URL inválida para ASTERDEx: {self.base_url}")

        if not self.api_key or not self.api_secret:
            self.logger.warning("Credenciales ASTERDEx incompletas; solo endpoints públicos estarán disponibles.")

    # ============================================================
    # Helpers internos
    # ============================================================
    @staticmethod
    def _canonical_query(params: Mapping[str, Any]) -> str:
        """Convierte un diccionario en query string ordenada."""
        pieces: list[str] = []
        for key in sorted(params.keys()):
            value = params[key]
            if value is None:
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            pieces.append(f"{key}={value}")
        return "&".join(pieces)

    def _sign(self, params: Mapping[str, Any]) -> str:
        if not self.api_secret:
            raise RuntimeError("No hay API secret configurado para firmar la petición.")
        query_string = self._canonical_query(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _headers(self, requires_api_key: bool = False) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if requires_api_key and self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        requires_api_key: bool = False,
        timeout: Optional[int] = None,
        _skip_time_sync: bool = False,
    ) -> Any:
        url = f"{self.base_url}{path}"
        payload: Dict[str, Any] = {}
        if params:
            payload.update({k: v for k, v in params.items() if v is not None})

        if signed:
            if not _skip_time_sync:
                self._sync_time()
            payload.setdefault("timestamp", int(time.time() * 1000 + self._time_offset_ms))
            payload.setdefault("recvWindow", self.recv_window)
            payload["signature"] = self._sign(payload)
            payload = dict(sorted(payload.items()))

        headers = self._headers(requires_api_key=requires_api_key or signed)
        response = self.session.request(
            method=method.upper(),
            url=url,
            params=payload if method.upper() in ("GET", "DELETE") else None,
            data=payload if method.upper() not in ("GET", "DELETE") else None,
            headers=headers,
            timeout=timeout or 10,
        )

        if response.status_code >= 400:
            payload = None
            try:
                payload = response.json()
            except Exception:
                payload = response.text
            raise AsterDexAPIError(response.status_code, payload)

        if not response.text:
            return {}

        try:
            return response.json()
        except ValueError:
            return response.text

    # ============================================================
    # Endpoints públicos
    # ============================================================
    def ping(self) -> Any:
        return self._request("GET", "/fapi/v1/ping")

    def get_server_time(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/time")

    def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        params = {"symbol": symbol.upper()} if symbol else None
        return self._request("GET", "/fapi/v1/exchangeInfo", params=params)

    def get_mark_price(self, symbol: Optional[str] = None) -> Any:
        params = {"symbol": symbol.upper()} if symbol else None
        return self._request("GET", "/fapi/v1/premiumIndex", params=params)

    def get_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Any:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self._request("GET", "/fapi/v1/klines", params=params)

    # ============================================================
    # Endpoints firmados
    # ============================================================
    def place_order(self, **params: Any) -> Any:
        """
        Envía POST /fapi/v1/order.

        Parámetros clave:
            symbol (str)   : requerido
            side (str)     : BUY / SELL
            type (str)     : MARKET, LIMIT, etc.
            quantity (str) : tamaño nominal (en contratos)
        """
        return self._request(
            "POST",
            "/fapi/v1/order",
            params=params,
            signed=True,
        )

    def get_order(self, **params: Any) -> Any:
        return self._request(
            "GET",
            "/fapi/v1/order",
            params=params,
            signed=True,
        )

    def cancel_order(self, **params: Any) -> Any:
        return self._request(
            "DELETE",
            "/fapi/v1/order",
            params=params,
            signed=True,
        )

    def get_open_orders(self, **params: Any) -> Any:
        return self._request(
            "GET",
            "/fapi/v1/openOrders",
            params=params,
            signed=True,
        )

    def get_account_balance(self) -> Any:
        return self._request(
            "GET",
            "/fapi/v2/balance",
            signed=True,
        )

    def get_account_information(self) -> Any:
        return self._request(
            "GET",
            "/fapi/v4/account",
            signed=True,
        )

    # ============================================================
    # Sincronización de tiempo
    # ============================================================
    def _sync_time(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_time_sync) < 60:
            return
        if not self.api_key or not self.api_secret:
            return
        try:
            response = self._request("GET", "/fapi/v1/time", _skip_time_sync=True)
        except Exception as exc:  # pragma: no cover - defensivo
            self.logger.debug("No se pudo sincronizar tiempo con ASTER: %s", exc)
            return
        server_time = int(response.get("serverTime", 0)) if isinstance(response, dict) else 0
        if server_time <= 0:
            return
        local_ms = int(time.time() * 1000)
        self._time_offset_ms = server_time - local_ms
        self._last_time_sync = now


__all__ = ["AsterDexClient", "AsterDexAPIError", "DEFAULT_BASE_URL"]
