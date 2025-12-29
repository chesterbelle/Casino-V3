"""
Quick cleanup script for orphaned positions and orders
Usage: python -m utils.cleanup_positions --exchange binance --mode demo
"""

import asyncio
import os

from dotenv import load_dotenv

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


async def cleanup_all(exchange="binance", mode="demo", symbol="LTCUSDT"):
    load_dotenv()

    if exchange == "binance":
        if mode == "demo":
            api_key = os.getenv("BINANCE_TESTNET_API_KEY")
            secret = os.getenv("BINANCE_TESTNET_SECRET")
        else:
            api_key = os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_API_SECRET")

        connector = BinanceNativeConnector(api_key=api_key, secret=secret, mode=mode)
        await connector.connect()

        print(f"🧹 Cleaning up {symbol} on {exchange} ({mode})...")

        # 1. Cancel all open orders
        try:
            orders = await connector.fetch_open_orders(symbol)
            print(f"📋 Found {len(orders)} open orders")
            for order in orders:
                try:
                    await connector.cancel_order(order["id"], symbol)
                    print(f"  ❌ Canceled order {order['id']} ({order.get('type')})")
                except Exception as e:
                    print(f"  ⚠️ Error canceling {order['id']}: {e}")
        except Exception as e:
            print(f"⚠️ Error fetching orders: {e}")

        # 2. Close all positions
        try:
            positions = await connector.fetch_positions(symbol)
            open_positions = [p for p in positions if abs(p.get("contracts", 0)) > 0]
            print(f"📊 Found {len(open_positions)} open positions")

            for pos in open_positions:
                try:
                    size = abs(pos.get("contracts", 0))
                    side = "sell" if pos.get("contracts", 0) > 0 else "buy"
                    position_side = "LONG" if pos.get("contracts", 0) > 0 else "SHORT"

                    await connector.create_order(
                        symbol=symbol,
                        order_type="market",
                        side=side,
                        amount=size,
                        params={"positionSide": position_side},
                    )
                    print(f"  🔨 Closed {position_side} position ({size} contracts)")
                except Exception as e:
                    print(f"  ⚠️ Error closing position: {e}")
        except Exception as e:
            print(f"⚠️ Error fetching positions: {e}")

        await connector.disconnect()
        print("✅ Cleanup complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--mode", default="demo")
    parser.add_argument("--symbol", default="LTCUSDT")
    args = parser.parse_args()

    asyncio.run(cleanup_all(args.exchange, args.mode, args.symbol))
