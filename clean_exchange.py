import asyncio
import os

from dotenv import load_dotenv

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


async def clean_all():
    load_dotenv()
    api_key = os.getenv("BINANCE_TESTNET_API_KEY")
    secret = os.getenv("BINANCE_TESTNET_SECRET")

    if not api_key or not secret:
        print("❌ Missing API keys.")
        return

    c = BinanceNativeConnector(api_key=api_key, secret=secret, mode="demo")
    await c.connect()

    print("🧹 Fetching positions...")
    ps = await c.fetch_positions()
    for p in ps:
        sz = abs(float(p.get("size", 0)))
        if sz > 0.0001:
            symbol = p["symbol"]
            side = "sell" if p.get("side") == "LONG" else "buy"
            print(f"📉 Closing {symbol}: {p['side']} {sz}")
            await c.create_order(symbol, "market", side, sz, params={"reduceOnly": "true"})

    print("🧹 Fetching orders...")
    # Testnet often has orphans in these symbols
    symbols = ["BTCUSDT", "LTCUSDT", "ETHUSDT", "SOLUSDT"]
    for s in symbols:
        try:
            orders = await c.fetch_open_orders(s)
            for o in orders:
                print(f"🚫 Cancelling {s} {o['id']}")
                await c.cancel_order(o["id"], s)
        except Exception as e:
            print(f"⚠️ Error cleaning {s}: {e}")

    await c.close()
    print("✨ Exchange Cleanup Complete.")


if __name__ == "__main__":
    asyncio.run(clean_all())
