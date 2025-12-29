import asyncio
import logging
import os
import re

# IMPORTANT: Import the actual connector
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("Sweep")


async def sweep():
    # Load .env
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    parts = line.strip().split("=", 1)
                    if len(parts) == 2:
                        k, v = parts
                        os.environ[k] = v.replace('"', "").strip()

    connector = BinanceNativeConnector(
        api_key=os.getenv("BINANCE_API_KEY"),
        secret=os.getenv("BINANCE_API_SECRET"),
        mode="demo",
        enable_websocket=False,
    )

    await connector.connect()

    logger.info("🔍 Fetching all open positions and orders...")
    positions, orders = await asyncio.gather(connector.fetch_positions(), connector.fetch_open_orders(None))

    active_positions = [p for p in positions if abs(float(p.get("contracts", 0) or 0)) > 1e-8]
    logger.info(f"Found {len(active_positions)} positions and {len(orders)} orders.")

    # 1. Cancel all orders
    if orders:
        logger.info(f"Cancelling {len(orders)} orders...")
        for o in orders:
            try:
                await connector.cancel_order(o["id"], o["symbol"])
                logger.info(f"✅ Cancelled order {o['id']} ({o['symbol']})")
            except Exception as e:
                logger.error(f"❌ Failed to cancel order {o['id']}: {e}")

    # 2. Close positions with SMART CLOSE Tiers
    if active_positions:
        logger.info(f"Closing {len(active_positions)} positions...")
        for pos in active_positions:
            symbol = pos["symbol"]
            size = abs(float(pos["contracts"]))
            side_raw = pos["side"].lower()
            close_side = "sell" if side_raw == "long" else "buy"

            logger.info(f"📉 Closing {symbol} {side_raw} {size}...")

            try:
                # Tier 0: Market
                await connector.create_market_order(
                    symbol=symbol, side=close_side, amount=size, params={"reduceOnly": True}
                )
                logger.info(f"✅ Closed {symbol} (Market)")
            except Exception as e:
                err_str = str(e)
                if "-4131" in err_str:
                    logger.warning("⚠️ Market blocked by -4131. Tier 1 Fallback (Aggressive Limit)...")
                    try:
                        ticker = await connector.fetch_ticker(symbol)
                        price = ticker["last"]
                        buffer = 0.95 if close_side == "sell" else 1.05
                        limit_price = float(connector.price_to_precision(symbol, price * buffer))

                        logger.info(f"🔄 Attempting Tier 1 LIMIT @ {limit_price}")
                        try:
                            await connector.create_order(
                                symbol=symbol,
                                side=close_side,
                                amount=size,
                                order_type="limit",
                                price=limit_price,
                                params={"timeInForce": "GTC"},
                            )
                            logger.info(f"✅ Closed {symbol} via Tier 1 LIMIT")
                        except Exception as t1_e:
                            t1_str = str(t1_e)
                            if "-4016" in t1_str:
                                logger.warning("⚠️ Tier 1 failed (-4016). Tier 2 (Price Band Regex)...")
                                match = re.search(r"higher than ([\d\.]+)", t1_str) or re.search(
                                    r"lower than ([\d\.]+)", t1_str
                                )
                                if match:
                                    band_price = float(match.group(1).rstrip("."))
                                    # Safe margin
                                    adj_price = band_price * 0.999 if "higher" in t1_str else band_price * 1.001
                                    target_price = float(connector.price_to_precision(symbol, adj_price))
                                    logger.info(f"🔄 Attempting Tier 2 LIMIT @ {target_price}")
                                    await connector.create_order(
                                        symbol=symbol,
                                        side=close_side,
                                        amount=size,
                                        order_type="limit",
                                        price=target_price,
                                        params={"timeInForce": "GTC"},
                                    )
                                    logger.info(f"✅ Closed {symbol} via Tier 2 LIMIT")
                                else:
                                    logger.error(f"❌ Could not parse Price Band from: {t1_str}")
                            else:
                                logger.error(f"❌ Tier 1 unexpected fail: {t1_e}")
                    except Exception as fallback_e:
                        logger.error(f"❌ Smart Close Failed: {fallback_e}")
                else:
                    logger.error(f"❌ Failed to close {symbol}: {e}")

    await connector.close()
    logger.info("🏁 Sweep Complete.")


if __name__ == "__main__":
    asyncio.run(sweep())
