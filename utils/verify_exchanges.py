import asyncio
import logging
import os
from typing import List

from exchanges.adapters import ExchangeAdapter
from exchanges.connectors import BinanceNativeConnector, HyperliquidNativeConnector

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ExchangeVerifier")


async def test_exchange(exchange_id: str, symbols: List[str]):
    """Prueba la conexión, obtención de balance y ejecución de una orden de prueba."""
    logger.info(f"\n{'='*60}\n🔬 Probando Exchange: {exchange_id.upper()}\n{'='*60}")
    connector = None
    try:
        # 1. Inicialización
        logger.info("1.1. Inicializando Connector...")

        if exchange_id == "binance":
            connector = BinanceNativeConnector(
                api_key=os.getenv("BINANCE_API_KEY"),
                secret=os.getenv("BINANCE_API_SECRET"),
                mode="demo",
            )
        elif exchange_id == "hyperliquid":
            connector = HyperliquidNativeConnector(
                api_key=os.getenv("HYPERLIQUID_API_SECRET"),
                account_address=os.getenv("HYPERLIQUID_MAIN_WALLET"),
                mode="demo",
            )
        else:
            raise ValueError(f"Exchange {exchange_id} no soportado")

        # Initialize Adapter (just to check instantiation)
        ExchangeAdapter(connector, symbol="BTC/USDT:USDT")
        logger.info("1.2. ✅ Adapter inicializado.")

        # 2. Conexión
        logger.info("2.1. Iniciando connector.connect()...")
        await connector.connect()
        logger.info(f"2.2. ✅ Conexión a {exchange_id} completada.")

        # 3. Balance
        logger.info("3.1. Iniciando fetch_balance()...")
        balance = await connector.fetch_balance()
        logger.info("3.2. ✅ Balance obtenido.")

        total_usdt = balance.get("total", {}).get("USDT", 0.0) or balance.get("total", {}).get("USDC", 0.0)
        logger.info(f"3.3. ✅ Balance procesado: {total_usdt:.4f} USDT/USDC")

        # 4. Orden de prueba (Simulada/Check de precio)
        logger.info("4.1. Verificando acceso a mercado...")
        test_symbol = symbols[0]

        # Fetch Ticker via Adapter/Connector
        ticker = await connector.fetch_ticker(test_symbol)
        price = ticker.get("last")
        logger.info(f"4.2. ✅ Precio actual de {test_symbol}: {price}")

        logger.info(f"\n{'='*25} 🎉 ÉXITO: {exchange_id.upper()} funciona correctamente {'='*25}")

    except Exception as e:
        logger.error(f"\n{'='*25} 🔥 FALLO: {exchange_id.upper()} no pasó la prueba {'='*25}")
        if "Wallet" in str(e) and "does not exist" in str(e):
            logger.error("Error: La wallet de Hyperliquid no existe o no está fondeada en el Testnet.")
            logger.warning("SOLUCIÓN: Visita https://app.hyperliquid-testnet.xyz/ y conecta tu wallet para activarla.")
        else:
            logger.error(f"Error: {e}", exc_info=True)
    finally:
        if connector:
            await connector.close()


async def main():
    """Punto de entrada principal para verificar todos los exchanges."""
    # Lista de exchanges y símbolos de prueba
    exchanges_to_test = [
        {"id": "binance", "symbols": ["BTC/USDT"]},
        {"id": "hyperliquid", "symbols": ["BTC/USDC"]},
    ]

    for exchange_info in exchanges_to_test:
        await test_exchange(exchange_info["id"], exchange_info["symbols"])


if __name__ == "__main__":
    asyncio.run(main())
