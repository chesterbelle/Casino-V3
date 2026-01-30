import asyncio
import json

import aiohttp

# import time


async def test_ws_subscribe_trades():
    url = "wss://stream.binancefuture.com/ws"
    print(f"Connecting to {url}...")
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            print("Connected!")
            subscribe_payload = {"method": "SUBSCRIBE", "params": ["ethusdt@aggTrade"], "id": 1}
            print(f"Sending: {subscribe_payload}")
            await ws.send_json(subscribe_payload)

            for _ in range(10):
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    print(f"Received: {data}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"Error: {ws.exception()}")
                    break
                else:
                    print(f"Other: {msg.type}")


if __name__ == "__main__":
    asyncio.run(test_ws_subscribe_trades())
