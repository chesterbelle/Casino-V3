import asyncio

from config.settings import load_config
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


async def main():
    cfg = load_config("demo")
    api_key = cfg.get("binance", {}).get("testnet", {}).get("api_key")
    secret = cfg.get("binance", {}).get("testnet", {}).get("api_secret")

    conn = BinanceNativeConnector(mode="demo", api_key=api_key, secret=secret)
    await conn.connect()

    positions = await conn.fetch_positions()
    for p in positions:
        size = float(p.get("size", 0))
        symbol = p.get("symbol")
        if abs(size) > 0:
            print(f"Closing {size} of {symbol}")
            side = "sell" if size > 0 else "buy"
            await conn.create_order(symbol=symbol, side=side, amount=abs(size), order_type="market")
            print(f"Closed {symbol}")

    await conn.close()
    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
