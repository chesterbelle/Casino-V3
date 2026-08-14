"""
ChaosBinanceConnector - Fault Injection Wrapper for BinanceNativeConnector
Solo se activa con CHAOS_MODE=1 (env var). Zero impacto en producción.
"""

import asyncio
import os
import random

import aiohttp

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


class ChaosBinanceConnector(BinanceNativeConnector):
    """BinanceNativeConnector con inyección de fallos controlada para Chaos Testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._chaos_mode = os.getenv("CHAOS_MODE", "0") == "1"

        if self._chaos_mode:
            # Config via env vars (defaults conservadores)
            self._chaos_fail_rate = float(os.getenv("CHAOS_FAIL_RATE", "0.15"))
            self._chaos_latency_ms = int(os.getenv("CHAOS_LATENCY_MS", "800"))
            self._chaos_timeout_rate = float(os.getenv("CHAOS_TIMEOUT_RATE", "0.08"))
            self.logger.warning("🌪️ CHAOS MODE ENABLED — Fault injection ACTIVE")

    async def _execute_raw_request(self, method, url, params, headers, endpoint_type, signed, timeout):
        # CHAOS INJECTION — Solo order writes (POST/PUT/DELETE a /order o /algoOrder)
        if self._chaos_mode:
            is_order_write = method in ("POST", "PUT", "DELETE") and ("/order" in url or "/algoOrder" in url)

            if is_order_write:
                # 1. Latencia simulada (50% requests)
                if random.random() < 0.5:
                    await asyncio.sleep(self._chaos_latency_ms / 1000)

                # 2. Fallo de red simulado (-1007, 502, connection reset)
                if random.random() < self._chaos_fail_rate:
                    error_type = random.choice(["-1007", "502", "ECONNRESET"])
                    raise aiohttp.ClientError(f"CHAOS: Simulated Binance failure ({error_type})")

                # 3. Timeout simulado (worker no responde en 0.5s -> grace period se activa)
                if random.random() < self._chaos_timeout_rate:
                    await asyncio.sleep(0.6)  # > Airlock timeout (0.5s)

        # Delega al metodo original (Airlock, fallback, etc.)
        return await super()._execute_raw_request(method, url, params, headers, endpoint_type, signed, timeout)
