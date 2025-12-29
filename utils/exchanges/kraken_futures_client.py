"""
Minimal REST client for Kraken Futures (v3 API).

Implements just enough functionality for the Casino live loop:
    • public market data (tickers, orderbook, candles via charts API)
    • private trading endpoints (sendorder, accounts, openorders, fills)
Signature logic mirrors ccxt.krakenfutures implementation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

DEFAULT_BASE_URL = "https://demo-futures.kraken.com/derivatives/api/"
DEFAULT_CHARTS_URL = "https://demo-futures.kraken.com/api/charts/v1/"
API_VERSION = "v3"


class KrakenFuturesAPIError(RuntimeError):
    """Error raised when Kraken Futures returns an error payload."""

    def __init__(self, message: str, payload: Any | None = None):
        super().__init__(message)
        self.payload = payload


class KrakenFuturesClient:
    """Ligero cliente REST orientado a paper trading con Kraken Futures."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        charts_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.logger = logging.getLogger("KrakenFuturesClient")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
        self.charts_url = (charts_url or DEFAULT_CHARTS_URL).rstrip("/") + "/"
        self.session = session or requests.Session()

        if not self.base_url.endswith("api/"):
            self.logger.warning("Base URL no parece apuntar al prefijo /api/: %s", self.base_url)

    # ---------------------------------------------------------------------
    # Public helpers
    # ---------------------------------------------------------------------
    def get_instruments(self) -> Dict[str, Any]:
        return self._request_public("instruments")

    def get_tickers(self) -> Dict[str, Any]:
        return self._request_public("tickers")

    def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        return self._request_public("orderbook", params={"symbol": symbol})

    def get_candles(
        self, symbol: str, interval: str = "1m", price_type: str = "trade", **params: Any
    ) -> Dict[str, Any]:
        """
        Recupera velas desde la API de charts.
        Intervalos válidos: 1m, 5m, 15m, 1h, etc (según doc oficial).
        """
        query = {"symbol": symbol, "interval": interval}
        query.update(params)
        url = f"{self.charts_url}{price_type}/{symbol}/{interval}"
        response = self.session.get(
            url, params={k: v for k, v in query.items() if k not in {"symbol", "interval"}}, timeout=10
        )
        return self._parse_response(response)

    # ---------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------
    def get_accounts(self) -> Dict[str, Any]:
        return self._request_private("accounts", method="GET")

    def get_open_orders(self) -> Dict[str, Any]:
        return self._request_private("openorders", method="GET")

    def get_recent_orders(self) -> Dict[str, Any]:
        return self._request_private("recentorders", method="GET")

    def get_fills(self) -> Dict[str, Any]:
        return self._request_private("fills", method="GET")

    def get_open_positions(self) -> Dict[str, Any]:
        return self._request_private("openpositions", method="GET")

    def send_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_private("sendorder", method="POST", params=payload)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self._request_private("cancelorder", method="POST", params={"order_id": order_id})

    # ---------------------------------------------------------------------
    # Internal request machinery
    # ---------------------------------------------------------------------
    def _request_public(
        self, path: str, params: Optional[Dict[str, Any]] = None, method: str = "GET"
    ) -> Dict[str, Any]:
        endpoint = f"{API_VERSION}/{path}"
        url = self.base_url + endpoint
        response = self.session.request(method.upper(), url, params=params, timeout=10)
        return self._parse_response(response)

    def _request_private(
        self, path: str, *, method: str = "POST", params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.api_key or not self.api_secret:
            raise KrakenFuturesAPIError("No API key/secret configured for private request.")

        endpoint = f"{API_VERSION}/{path}"
        url = self.base_url + endpoint
        params = params or {}

        if method.upper() in ("GET", "DELETE"):
            encoded = urlencode(params)
            request_url = url if not encoded else f"{url}?{encoded}"
            auth_payload = encoded + "/api/" + endpoint if encoded else "/api/" + endpoint
            body = None
        else:
            encoded = urlencode(params)
            request_url = url
            body = encoded
            auth_payload = encoded + "/api/" + endpoint

        signature = self._sign(auth_payload)
        headers = {
            "Accept": "application/json",
            "APIKey": self.api_key,
            "Authent": signature,
        }
        if method.upper() not in ("GET", "DELETE"):
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        response = self.session.request(method.upper(), request_url, data=body, timeout=10, headers=headers)
        return self._parse_response(response)

    def _sign(self, payload: str) -> str:
        """
        Firma basada en la especificación de Kraken Futures (CryptoFacilities).
        signature = base64( HMAC_SHA512( SHA256(payload), decoded_secret ) )
        """
        secret = base64.b64decode(self.api_secret)
        digest = hashlib.sha256(payload.encode("utf-8")).digest()
        signature = hmac.new(secret, digest, hashlib.sha512).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _parse_response(self, response: requests.Response) -> Dict[str, Any]:
        text = response.text or ""
        try:
            data = response.json() if text else {}
        except ValueError as exc:
            raise KrakenFuturesAPIError(f"Respuesta inválida de Kraken Futures: {text}") from exc

        if response.status_code >= 400:
            raise KrakenFuturesAPIError(f"HTTP {response.status_code}: {data}", data)

        # Algunos endpoints devuelven {"result": "...", ...}
        result = data.get("result")
        if isinstance(result, str) and result.lower() == "error":
            raise KrakenFuturesAPIError(f"Kraken Futures error: {data}", data)

        error = data.get("error") or data.get("errors")
        if error:
            raise KrakenFuturesAPIError(f"Kraken Futures error: {error}", data)

        return data
