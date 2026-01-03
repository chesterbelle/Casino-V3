import asyncio
import os

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector


async def main():
    # Initialize connector
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    connector = BinanceNativeConnector(api_key=api_key, secret=api_secret, mode="demo", enable_websocket=False)
    await connector.connect()

    # Fetch Position Entry Price
    positions = await connector.fetch_positions()
    ltc_pos = next((p for p in positions if "LTC" in p["symbol"]), None)

    if ltc_pos:
        print(f"✅ Position Found: {ltc_pos['symbol']}")
        print(f"   Amt: {ltc_pos['positionAmt']}")
        print(f"   Entry: {ltc_pos['entryPrice']}")
        entry_price = float(ltc_pos["entryPrice"])
    else:
        print("❌ No LTC position found")
        return

    # Fetch Order 905594242
    try:
        # Note: connector.get_orders might catch open orders.
        # We specifically want to check the details of this ID.
        orders = await connector.fetch_open_orders(None)
        sl_order = next(
            (o for o in orders if str(o.get("orderId")) == "905594242" or str(o.get("clientOrderId")) == "905594242"),
            None,
        )

        if sl_order:
            print(f"✅ SL Order Found: {sl_order['orderId']}")
            print(f"   Type: {sl_order['type']}")
            # stopPrice might be in different fields depending on endpoint info
            stop_price_val = sl_order.get("stopPrice")
            print(f"   Stop Price: {stop_price_val}")

            stop_price = float(stop_price_val)
            diff = abs(entry_price - stop_price)
            pct = diff / entry_price * 100

            print("\n📊 ANALYSIS:")
            print(f"   Entry: {entry_price}")
            print(f"   Stop:  {stop_price}")
            print(f"   Diff:  {diff:.4f}")
            print(f"   PCT:   {pct:.2f}%")

            if pct > 5.0:
                print("\n🔥 CONCLUSION: Order > 5% VALIDATED. My previous limit theory was wrong.")
            else:
                print("\n❄️ CONCLUSION: Order is within 5%.")

        else:
            print("❌ Order 905594242 not found in open orders")
            # Try fetch explicitly if connector has method, or just raw request
            # Using raw request for certainty if possible, but connector abstraction is safer first.

    except Exception as e:
        print(f"Error: {e}")

    await connector.close()


if __name__ == "__main__":
    asyncio.run(main())
