"""
Prometheus Metrics HTTP Server.

Exposes metrics on /metrics endpoint for Prometheus scraping.

Author: Casino V3 Team
Version: 2.0.0
"""

import asyncio
import logging
from typing import Optional

from prometheus_client import REGISTRY, generate_latest, make_asgi_app

logger = logging.getLogger(__name__)


class MetricsServer:
    """
    HTTP server for Prometheus metrics.

    Example:
        server = MetricsServer(port=8000)
        await server.start()

        # Metrics available at http://localhost:8000/metrics

        await server.stop()
    """

    def __init__(self, port: int = 8000, host: str = "0.0.0.0"):
        """
        Initialize metrics server.

        Args:
            port: Port to listen on
            host: Host to bind to
        """
        self.port = port
        self.host = host
        self._server: Optional[asyncio.Server] = None
        self._app = make_asgi_app(REGISTRY)

    async def start(self):
        """Start the metrics server."""
        try:
            # Simple HTTP server using asyncio
            from aiohttp import web

            app = web.Application()

            async def metrics_handler(request):
                """Handle /metrics requests."""
                metrics = generate_latest(REGISTRY)
                return web.Response(body=metrics, content_type="text/plain")

            async def health_handler(request):
                """Handle /health requests."""
                return web.Response(text="OK")

            app.router.add_get("/metrics", metrics_handler)
            app.router.add_get("/health", health_handler)

            runner = web.AppRunner(app)
            await runner.setup()

            site = web.TCPSite(runner, self.host, self.port)
            await site.start()

            self._server = runner

            logger.info(f"📊 Metrics server started on http://{self.host}:{self.port}/metrics")

        except Exception as e:
            logger.error(f"❌ Failed to start metrics server: {e}")
            raise

    async def stop(self):
        """Stop the metrics server."""
        if self._server:
            await self._server.cleanup()
            logger.info("🛑 Metrics server stopped")


# Singleton instance
_metrics_server: Optional[MetricsServer] = None


async def start_metrics_server(port: int = 8000, host: str = "0.0.0.0"):
    """
    Start global metrics server.

    Args:
        port: Port to listen on
        host: Host to bind to
    """
    global _metrics_server

    if _metrics_server is not None:
        logger.warning("⚠️ Metrics server already running")
        return

    _metrics_server = MetricsServer(port=port, host=host)
    await _metrics_server.start()


async def stop_metrics_server():
    """Stop global metrics server."""
    global _metrics_server

    if _metrics_server is not None:
        await _metrics_server.stop()
        _metrics_server = None
