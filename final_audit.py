import asyncio
import os
import sys

# Add root to sys.path
sys.path.append(os.getcwd())

from utils.validators.multi_symbol_validator import MultiSymbolValidator  # noqa: E402


async def run_final_audit():
    symbols = [
        "ETH/USDT:USDT",
        "XRP/USDT:USDT",
        "BCH/USDT:USDT",
        "LTC/USDT:USDT",
        "ETC/USDT:USDT",
        "LINK/USDT:USDT",
        "XLM/USDT:USDT",
        "ADA/USDT:USDT",
        "RUNE/USDT:USDT",
        "DASH/USDT:USDT",
    ]

    validator = MultiSymbolValidator(symbols=symbols, mode="demo")
    await validator.setup()

    print("\n" + "=" * 50)
    print(" 🔍 FINAL CRASH AUDIT & SWEEP")
    print("=" * 50)

    # Perform emergency sweep to close any lingering positions
    print(f"🧹 Performing emergency sweep for {len(symbols)} symbols...")
    report = await validator.croupier.emergency_sweep(close_positions=True)

    print("\n✅ Sweep Report:")
    print(f"   - Positions Closed: {report['positions_closed']}")
    print(f"   - Orders Cancelled: {report['orders_cancelled']}")
    print(f"   - Symbols Processed: {', '.join(report['symbols_processed'])}")

    if report["errors"]:
        print("\n❌ Errors encountered:")
        for err in report["errors"]:
            print(f"   - {err}")

    print("\n" + "=" * 50)
    await validator.connector.close()


if __name__ == "__main__":
    asyncio.run(run_final_audit())
