import asyncio
import logging
import os

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Audit")


async def audit():
    # Load .env manually
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v.replace('"', "").strip()

    connector = BinanceNativeConnector(
        api_key=os.getenv("BINANCE_API_KEY"),
        secret=os.getenv("BINANCE_API_SECRET"),
        mode="demo",
        enable_websocket=False,
    )

    await connector.connect()
    # 1. Discover Active Symbols (EVERYTHING on Exchange)
    logger.info("Discovering active symbols (positions or orders)...")
    active_symbols = await connector.fetch_active_symbols()
    logger.info(f"Checking {len(active_symbols)} active symbols: {active_symbols}")

    orphans = 0
    zombies = 0

    for symbol in active_symbols:
        # Fetch status for each symbol
        positions = await connector.fetch_positions(symbol)
        symbol_pos = [p for p in positions if abs(float(p.get("contracts", 0))) > 1e-8]

        orders = await connector.fetch_open_orders(symbol)
        count = len(orders)

        # Analysis: Recognize limit (used for TP), stop_market/stop (used for SL)
        tps = [o for o in orders if o["type"] in ["take_profit_market", "take_profit", "limit"]]
        sls = [o for o in orders if o["type"] in ["stop_market", "stop"]]
        others = [o for o in orders if o not in tps and o not in sls]

        has_pos = len(symbol_pos) > 0
        side = symbol_pos[0]["side"].upper() if has_pos else "NONE"
        pos_amt = abs(float(symbol_pos[0].get("contracts", 0))) if has_pos else 0

        status = "✅ OK"
        if has_pos:
            # We expect at least 1 TP and 1 SL for a healthy managed position
            if len(tps) < 1 or len(sls) < 1:
                status = "❌ BROKEN OCO"
                orphans += 1
            elif count > 2:
                status = "⚠️ EXTRA ORDERS"
                orphans += count - 2
        else:
            status = "🧟 ZOMBIE (Orders without Position)"
            zombies += count

        logger.info(
            f"{symbol:12} [{side:5}] | Pos: {pos_amt:8.2f} | Orders: {count} (TP={len(tps)}, SL={len(sls)}) -> {status}"
        )

        logger.info(
            f"{symbol} [{side}]: {count} orders (TP={len(tps)}, SL={len(sls)}, Other={len(others)}) -> {status}"
        )

        if others:
            for o in others:
                logger.warning(f"   ⚠️ Stray Order: {o['id']} {o['type']} {o['side']}")

    logger.info(f"Summary: Symbols Checked={len(active_symbols)}, Potential Orphans/Zombies={orphans+zombies}")


if __name__ == "__main__":
    asyncio.run(audit())
