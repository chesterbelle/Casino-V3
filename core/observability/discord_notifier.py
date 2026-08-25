import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """
    Cliente asíncrono para enviar notificaciones a Discord mediante Webhooks.
    No bloquea el event loop del bot de trading.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        # Toma la URL de los argumentos o del entorno
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self._session: Optional[aiohttp.ClientSession] = None

        if not self.webhook_url:
            logger.warning("⚠️ DISCORD_WEBHOOK_URL no configurado. Las notificaciones de Discord están desactivadas.")

    async def start(self):
        """Inicializa la sesión de aiohttp."""
        if self.webhook_url and self._session is None:
            self._session = aiohttp.ClientSession()
            logger.info("✅ Discord Notifier iniciado.")

    async def close(self):
        """Cierra la sesión limpiamente."""
        if self._session:
            await self._session.close()
            self._session = None

    async def send_message(self, content: str, embeds: list = None):
        """
        Envía un mensaje al canal de Discord configurado.

        Args:
            content (str): Texto principal del mensaje.
            embeds (list): Lista de diccionarios con formato Rich Embed de Discord.
        """
        if not self.webhook_url or not self._session:
            return

        payload = {}
        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds

        try:
            async with self._session.post(self.webhook_url, json=payload) as response:
                if response.status not in (200, 204):
                    logger.error(f"❌ Error enviando a Discord. Status: {response.status}")
        except Exception as e:
            logger.error(f"❌ Excepción al notificar a Discord: {e}")

    async def notify_trade_opened(self, symbol: str, side: str, price: float, risk_pct: float):
        """Notificación rápida cuando se abre un trade."""
        color = 0x00FF00 if side.upper() == "LONG" else 0xFF0000
        embed = {
            "title": f"🚀 Trade Abierto: {symbol}",
            "color": color,
            "fields": [
                {"name": "Side", "value": side.upper(), "inline": True},
                {"name": "Entry Price", "value": f"${price:,.4f}", "inline": True},
                {"name": "Risk", "value": f"{risk_pct:.2f}%", "inline": True},
            ],
        }
        await self.send_message(content="", embeds=[embed])

    async def notify_trade_closed(self, symbol: str, pnl: float, exit_reason: str):
        """Notificación cuando se cierra un trade."""
        color = 0x00FF00 if pnl > 0 else 0xFF0000
        embed = {
            "title": f"🏁 Trade Cerrado: {symbol}",
            "color": color,
            "fields": [
                {"name": "PnL", "value": f"${pnl:,.2f}", "inline": True},
                {"name": "Razón", "value": exit_reason, "inline": True},
            ],
        }
        await self.send_message(content=f"Resultado en {symbol}: **${pnl:,.2f}** ({exit_reason})", embeds=[embed])

    async def notify_error(self, error_msg: str):
        """Notificación de errores críticos."""
        embed = {"title": "⚠️ Error Crítico en el Bot", "color": 0xFFA500, "description": str(error_msg)}
        await self.send_message(content="<@here> Se ha detectado una anomalía.", embeds=[embed])


# Instancia global por defecto
discord_notifier = DiscordNotifier()
