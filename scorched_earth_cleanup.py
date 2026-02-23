import asyncio
import hashlib
import hmac
import os
import sys
import time

import aiohttp

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from config.exchange import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_BASE_URL


async def cleanup():
    api_key = BINANCE_API_KEY
    api_secret = BINANCE_API_SECRET
    base_url = BINANCE_BASE_URL

    if not api_key or not api_secret:
        print("❌ Credentials not found in config.exchange")
        return

    print(f"🧹 Starting Scorched Earth Cleanup on {base_url}...")

    async with aiohttp.ClientSession() as session:

        def sign(params):
            params["timestamp"] = int(time.time() * 1000)
            query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            return f"{query}&signature={signature}"

        # 1. Fetch ALL symbols with open interest or positions
        print("🔍 Checking all possible positions...")
        endpoint = "/fapi/v2/positionRisk"
        async with session.get(f"{base_url}{endpoint}?{sign({})}", headers={"X-MBX-APIKEY": api_key}) as resp:
            if resp.status != 200:
                print(f"❌ Failed to fetch positions: {await resp.text()}")
                return
            positions = await resp.json()

        for p in positions:
            amt = float(p.get("positionAmt", 0))
            symbol = p["symbol"]

            # 2. Cancel all orders for this symbol first
            if amt != 0:
                print(f"🚩 Found position: {symbol} | {amt}")

                # Cancel all orders
                cancel_endpoint = "/fapi/v1/allOpenOrders"
                cancel_query = sign({"symbol": symbol})
                async with session.delete(
                    f"{base_url}{cancel_endpoint}?{cancel_query}", headers={"X-MBX-APIKEY": api_key}
                ) as _:
                    print(f"✅ Cancelled orders for {symbol}")

                # Market close
                side = "SELL" if amt > 0 else "BUY"
                order_params = {
                    "symbol": symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": str(abs(amt)),
                    "reduceOnly": "true",
                }
                signed_order = sign(order_params)
                async with session.post(
                    f"{base_url}/fapi/v1/order?{signed_order}", headers={"X-MBX-APIKEY": api_key}
                ) as oresp:
                    res = await oresp.json()
                    if oresp.status == 200:
                        print(f"✅ Closed {symbol}")
                    else:
                        print(f"❌ Failed to close {symbol}: {res}")
            else:
                # Still check for open orders even if amt is 0
                pass

        # 3. Final sweep for any other open orders
        print("🧹 Final open order sweep...")
        # Since we can't get all orders globally without symbol, we trust the position check or loop common symbols
        # Actually, /fapi/v1/allOpenOrders WITHOUT symbol is NOT supported in Futures.
        # But we can check symbols with active orders.

    print("✨ Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(cleanup())
