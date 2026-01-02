import asyncio
import logging
import os

from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Audit")


def super_normalize(symbol: str) -> str:
    """Extra aggressive normalization for audit purposes."""
    if not symbol:
        return ""
    # Strip suffixes and separators
    s = symbol.replace("/USDT", "").replace(":USDT", "").replace("/", "").replace(":", "").upper()
    # Ensure it ends up as just BASEUSDT or BASE
    if not s.endswith("USDT"):
        s += "USDT"
    return s


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

    # 1. Fetch EVERYTHING globally once (The "Source of Truth")
    logger.info("Fetching raw positions and orders from exchange...")
    raw_positions = await connector.fetch_positions()
    raw_orders = await connector.fetch_open_orders(None)

    # 2. Group by UNIQUE KEY (Symbol + ID) to prevent collisions
    # This is the FIX for the 'missing orders' bug
    unique_orders = {}
    for o in raw_orders:
        symbol = o["symbol"]
        oid = o["id"]
        key = f"{symbol}_{oid}"
        unique_orders[key] = o

    logger.info(f"Retrieved {len(unique_orders)} unique orders from exchange.")

    # 3. Group Positions by Super-Normalized Symbol
    positions_by_symbol = {}
    for pos in raw_positions:
        amt = float(pos.get("contracts", 0))
        if amt != 0:
            norm_sym = super_normalize(pos["symbol"])
            positions_by_symbol[norm_sym] = pos

    # 4. Group Orders by Super-Normalized Symbol
    orders_by_symbol = {}
    for o in unique_orders.values():
        norm_sym = super_normalize(o["symbol"])
        if norm_sym not in orders_by_symbol:
            orders_by_symbol[norm_sym] = []
        orders_by_symbol[norm_sym].append(o)

    # 5. Full Sweep (Union of symbols from positions AND orders)
    active_symbols = sorted(list(set(positions_by_symbol.keys()) | set(orders_by_symbol.keys())))
    logger.info(f"Auditing {len(active_symbols)} symbols with activity...")

    orphans = 0
    zombies = 0

    for symbol in active_symbols:
        symbol_pos = positions_by_symbol.get(symbol)
        symbol_orders = orders_by_symbol.get(symbol, [])

        count = len(symbol_orders)
        # Identify TPs and SLs
        tps = [o for o in symbol_orders if o["type"] in ["take_profit_market", "take_profit", "limit"]]
        sls = [o for o in symbol_orders if o["type"] in ["stop_market", "stop"]]
        others = [o for o in symbol_orders if o not in tps and o not in sls]

        has_pos = symbol_pos is not None
        side = symbol_pos["side"].upper() if has_pos else "NONE"
        pos_amt = abs(float(symbol_pos.get("contracts", 0))) if has_pos else 0

        status = "✅ OK"
        if has_pos:
            if len(tps) < 1 or len(sls) < 1:
                status = "❌ BROKEN OCO (Missing TP or SL)"
                orphans += 1
            elif count > 2:
                status = f"⚠️ EXTRA ORDERS ({count} orders for 1 position)"
                orphans += count - 2
        else:
            status = "🧟 ZOMBIE (Orders without active Position)"
            zombies += count

        logger.info(
            f"{symbol:12} [{side:5}] | Pos: {pos_amt:8.2f} | Orders: {count} (TP={len(tps)}, SL={len(sls)}) -> {status}"
        )

        for o in symbol_orders:
            is_algo = o.get("is_algo") or o["type"] in ["stop_market", "take_profit_market"]
            type_tag = "[ALGO]" if is_algo else "[REG ]"
            logger.info(f"   - {type_tag} {o['side'].upper():5} | {o['type']:18} | ID: {o['id']}")

        if others:
            for o in others:
                logger.warning(f"   ⚠️ Unexpected Order Type: {o['id']} {o['type']}")

    logger.info("-" * 50)
    logger.info("FINAL REPORT:")
    logger.info(f"  Symbols with activity: {len(active_symbols)}")
    logger.info(f"  Total orders found:    {len(unique_orders)}")
    logger.info(f"  Broken OCOs:           {orphans}")
    logger.info(f"  Zombies:               {zombies}")
    logger.info("-" * 50)


if __name__ == "__main__":
    asyncio.run(audit())
