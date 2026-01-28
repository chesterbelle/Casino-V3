import asyncio
import logging

import aiohttp
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WS_TEST")


async def test_websockets_lib():
    url = "wss://stream.binancefuture.com/ws/btcusdt@aggTrade"
    logger.info(f"Testing websockets lib connect to {url}...")
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            logger.info("✅ websockets lib connected!")
            msg = await ws.recv()
            logger.info(f"Received: {msg[:50]}...")
    except Exception as e:
        logger.error(f"❌ websockets lib failed: {e}")


async def test_aiohttp_lib():
    url = "wss://stream.binancefuture.com/ws/btcusdt@aggTrade"
    logger.info(f"Testing aiohttp lib connect to {url}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url) as ws:
                logger.info("✅ aiohttp lib connected!")
                msg = await ws.receive_str()
                logger.info(f"Received: {msg[:50]}...")
    except Exception as e:
        logger.error(f"❌ aiohttp lib failed: {e}")


async def main():
    logger.info("--- STARTING COMPARISON ---")
    await test_websockets_lib()
    logger.info("---")
    await test_aiohttp_lib()
    logger.info("--- DONE ---")


if __name__ == "__main__":
    asyncio.run(main())
