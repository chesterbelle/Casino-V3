import asyncio
import logging
import os
import sys
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import exchange as exchange_config
from croupier.croupier import Croupier
from exchanges.adapters import ExchangeAdapter
from exchanges.connectors.binance.binance_native_connector import BinanceNativeConnector

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("HealValidator")


async def run_validator():
    logger.info("🚀 Starting Auto-Healing Validator...")

    symbol = "LTCUSDT"
    connector = BinanceNativeConnector(
        api_key=exchange_config.BINANCE_API_KEY, secret=exchange_config.BINANCE_API_SECRET, mode="demo"
    )
    await connector.connect()

    adapter = ExchangeAdapter(connector, symbol)

    # 1. Initialize Croupier
    balance_data = await connector.fetch_balance()
    initial_balance = balance_data.get("total", {}).get("USDT", 0.0)

    croupier = Croupier(exchange_adapter=adapter, initial_balance=initial_balance)
    await croupier.start()

    # Lower audit interval for fast test
    croupier.drift_auditor.audit_interval = 5
    logger.info(f"⚙️ Test Audit Interval: {croupier.drift_auditor.audit_interval}s")

    # TEST 1: Balance Drift
    logger.info("🧪 TEST 1: Inducing Balance Drift...")
    # Artificially shift local balance by $10
    croupier.balance_manager.set_balance(initial_balance + 10.0)
    logger.info(f"💾 Local Balance poisoned to: {croupier.balance_manager.get_balance()}")

    logger.info("⏳ Waiting for DriftAuditor to detect and heal...")

    # Wait for up to 2 audit cycles
    found_healing = False
    for i in range(15):
        await asyncio.sleep(1)
        current_balance = croupier.balance_manager.get_balance()
        # Reconciliation should pull the real balance from exchange
        if abs(current_balance - initial_balance) < 0.1:
            logger.info(f"🎊 SUCCESS: DriftAuditor detected drift and healed balance to {current_balance}")
            found_healing = True
            break

    if not found_healing:
        logger.error(f"❌ FAILURE: Balance drift not healed. Current: {croupier.balance_manager.get_balance()}")

    # TEST 2: Position Discrepancy (Manual Order)
    logger.info("🧪 TEST 2: Inducing Position Count Drift (Manual Exchange Order)...")
    # Open a small position manually on exchange
    # (Using 5.5 USDT as minimum notional for Testnet is usually 5)
    amount = 0.1  # ~ $6.5
    logger.info(f"📤 Placing manual exchange order for {amount} {symbol}...")
    await connector.create_order(symbol=symbol, side="buy", order_type="market", amount=amount)

    logger.info("⏳ Waiting for DriftAuditor to detect discrepancy...")

    found_pos_healing = False
    for i in range(20):
        await asyncio.sleep(1)
        # Reconciliation should see the new position and Adopt it (or at least acknowledge it)
        # Even if it just logs the sync, our DriftAuditor triggers reconcile_all.
        if len(croupier.position_tracker.open_positions) > 0:
            logger.info(
                f"🎊 SUCCESS: DriftAuditor triggered sync and detected {len(croupier.position_tracker.open_positions)} positions!"
            )
            found_pos_healing = True
            break

    if not found_pos_healing:
        logger.error("❌ FAILURE: Position count drift not detected or healed.")

    # Cleanup
    logger.info("🧹 Final Cleanup...")
    await connector.create_order(symbol=symbol, side="sell", order_type="market", amount=amount)
    await croupier.stop()
    await connector.close()


if __name__ == "__main__":
    asyncio.run(run_validator())
