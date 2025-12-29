"""
Test Connection Utility
Prueba conexión básica con exchanges via Native SDKs
"""

import os
import sys

# Agregar directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import logging

from exchanges.adapters import ExchangeAdapter
from exchanges.connectors import BinanceNativeConnector, HyperliquidNativeConnector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ConnectionTester")


async def test_exchange_connection(exchange: str, testnet: bool = True):
    """Prueba conexión WebSocket y REST con el exchange."""
    try:
        logger.info(f"🔄 Probando conexión con {exchange.upper()} (testnet={testnet})")

        # 1. Conexión básica
        if exchange == "binance":
            connector = BinanceNativeConnector(
                api_key=os.getenv("BINANCE_API_KEY"),
                secret=os.getenv("BINANCE_API_SECRET"),
                mode="demo" if testnet else "live",
            )
        elif exchange == "hyperliquid":
            connector = HyperliquidNativeConnector(
                api_key=os.getenv("HYPERLIQUID_API_SECRET"),
                account_address=os.getenv("HYPERLIQUID_MAIN_WALLET"),
                mode="demo" if testnet else "live",
            )
        else:
            raise ValueError(f"Exchange {exchange} no soportado")

        # 2. WebSocket
        logger.info("🌐 Probando WebSocket...")
        await connector.connect()

        # 3. REST API (via Adapter)
        logger.info("📡 Probando API REST (Balance)...")
        balance = await connector.fetch_balance()

        # Normalize balance check
        total_usdt = balance.get("total", {}).get("USDT", 0.0) or balance.get("total", {}).get("USDC", 0.0)
        logger.info(f"💰 Balance: {total_usdt} (USDT/USDC)")

        logger.info("🎉 ¡Prueba exitosa!")

    except Exception as e:
        logger.error(f"❌ Error de conexión: {e}", exc_info=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", required=True, choices=["binance", "hyperliquid"])
    parser.add_argument("--testnet", type=bool, default=True)
    args = parser.parse_args()

    asyncio.run(test_exchange_connection(args.exchange, args.testnet))


if __name__ == "__main__":
    main()
