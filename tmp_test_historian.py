import asyncio

from core.observability.historian import historian


async def test():
    print("Recording trade...")
    historian.record_trade(
        {
            "trade_id": "1002690554",
            "symbol": "LTCUSDT",
            "side": "SELL",
            "entry_price": 54.0,
            "exit_price": 54.05,
            "pnl": 0.0,
            "fee": 0.0,
            "funding": 0.0,
            "exit_reason": "TP_SL_HIT",
            "qty": 0.484,
            "notional": 26.13,
            "session_id": "test_session",
        }
    )

    # Let MP worker process the queue
    await asyncio.sleep(2)

    print("Updating trade fee...")
    historian.update_trade_fee("1002690554", 0.0105)

    await asyncio.sleep(1)

    with historian._get_conn() as conn:
        c = conn.execute("SELECT * FROM trades")
        print("Trades in DB:", len(c.fetchall()))

    import logging

    logging.basicConfig(level=logging.DEBUG)

    # Trigger shutdown explicitly to see if it fixes things
    historian.stop()


if __name__ == "__main__":
    asyncio.run(test())
