import asyncio
import os
import sys

sys.path.append(os.getcwd())

from config import exchange as ex_cfg
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


async def check():
    c = BinanceNativeConnector(api_key=ex_cfg.BINANCE_API_KEY, secret=ex_cfg.BINANCE_API_SECRET, mode="demo")
    await c.connect()
    positions = await c.fetch_positions()
    print(f"POSITIONS: {positions}")
    await c.close()


if __name__ == "__main__":
    asyncio.run(check())
