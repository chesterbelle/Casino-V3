#!/usr/bin/env python3
"""
Test script to validate position closure detection in demo mode.

This script:
1. Opens a position with aggressive TP/SL (0.2% TP, 0.5% SL)
2. Monitors for 5 candles to detect closure
3. Verifies that the closure is detected and logged
"""

import asyncio
import logging

from core.data_sources.testing import TestingDataSource
from exchanges.connectors.binance.binance_connector import BinanceConnector
from exchanges.connectors.resilient_connector import ResilientConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")


async def main():
    print("=" * 80)
    print("🧪 TESTING POSITION CLOSURE DETECTION")
    print("=" * 80)
    print()

    # Create connector
    base_connector = BinanceConnector(mode="testnet")
    connector = ResilientConnector(connector=base_connector)

    # Create data source
    source = TestingDataSource(connector=connector, symbol="LTC/USD:USD", timeframe="1m", poll_interval=5.0)

    try:
        # Connect
        print("📡 Connecting to Binance Testnet...")
        await source.connect()
        print(f"✅ Connected | Balance: ${source.get_balance():.2f}")
        print()

        # Get first candle
        print("⏳ Waiting for first candle...")
        candle = await source.next_candle()
        print(f"✅ Candle received | Price: ${candle.close:.2f}")
        print()

        # Create order with AGGRESSIVE TP/SL
        print("📝 Creating order with aggressive TP/SL...")
        print("   TP: 0.2% (very close)")
        print("   SL: 0.5% (very close)")
        order = {
            "symbol": "LTC/USD:USD",
            "side": "LONG",
            "size": 0.0025,  # 0.25% of equity
            "take_profit": 1.002,  # 0.2% profit
            "stop_loss": 0.995,  # 0.5% loss
            "leverage": 10,
        }

        result = await source.execute_order(order)

        if result.get("status") != "opened":
            print(f"❌ Order failed: {result.get('reason')}")
            return

        print(f"✅ Position opened!")
        print(f"   Entry: ${result.get('entry_price'):.2f}")
        print(f"   Amount: {result.get('amount'):.4f}")
        print(f"   TP: ${result.get('entry_price') * 1.002:.2f}")
        print(f"   SL: ${result.get('entry_price') * 0.995:.2f}")
        print()

        # Monitor for 5 candles
        print("🔍 Monitoring for position closure (5 candles)...")
        print("   Checking every candle if TP/SL was executed...")
        print()

        for i in range(5):
            candle = await source.next_candle()
            print(f"📊 Candle {i+1}/5 | Price: ${candle.close:.2f} | Balance: ${candle.balance:.2f}")

            # Check if position is still tracked
            if "LTC/USD:USD" not in source._tracked_positions:
                print()
                print("🎯 POSITION CLOSURE DETECTED!")
                print("   The position was closed by TP or SL")
                break
        else:
            print()
            print("⏱️  Position still open after 5 candles")
            print("   TP/SL not executed yet (price didn't reach levels)")

        print()
        print("📊 Final Stats:")
        stats = await source.get_stats()
        print(f"   Balance: ${stats['final_balance']:.2f}")
        print(f"   PnL: ${stats['total_pnl']:+.2f}")
        print(f"   Trades: {stats['total_trades']}")
        print(f"   Open Positions: {stats['open_positions']}")

    finally:
        print()
        print("🔌 Disconnecting...")
        await source.disconnect()
        print("✅ Test completed")


if __name__ == "__main__":
    asyncio.run(main())
