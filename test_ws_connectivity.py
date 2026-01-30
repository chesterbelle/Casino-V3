import asyncio
import json

import aiohttp

# import time


async def test_ws():
    url = "wss://stream.binancefuture.com/ws/ethusdt@ticker"
    print(f"Connecting to {url}...")
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            print("Connected!")
            for _ in range(5):
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    print(f"Received: {data.get('s')} | {data.get('c')}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"Error: {ws.exception()}")
                    break
                else:
                    print(f"Other: {msg.type}")


if __name__ == "__main__":
    asyncio.run(test_ws())
