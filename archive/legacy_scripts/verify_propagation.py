import asyncio
import logging

from core.observability.historian import historian


async def verify_stats():
    # Load stats from DB
    session_stats = await historian.get_session_stats(session_id="backtest")
    setup_stats = await historian.get_setup_stats(session_id="backtest")
    detailed_report = await historian.get_detailed_report(session_id="backtest")

    print("\n" + "=" * 60)
    print("📊 VERIFICATION: SETUP_TYPE ATTRIBUTION")
    print("=" * 60)
    print(f"Global Trades: {session_stats.get('count', 0)}")

    print("\n--- Stats by Setup Type ---")
    for s in setup_stats:
        print(
            f"Setup: {s.get('setup_type', 'unknown')} | Trades: {s.get('count', 0)} | Net PnL: ${s.get('total_net_pnl', 0.0):+.2f}"
        )

    print("\n--- Detailed Report (First 5 Rows) ---")
    for row in detailed_report[:5]:
        print(
            f"Symbol: {row.get('symbol')} | Setup: {row.get('setup_type')} | Win Rate: {row.get('win_rate', 0.0):.1f}%"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(verify_stats())
