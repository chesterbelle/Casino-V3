import asyncio
import logging

from tardis_dev import download_datasets_async

logging.basicConfig(level=logging.INFO)


async def test_download():
    # Test downloading 1 day of LTCUSDT trades (first of month is free)
    await download_datasets_async(
        exchange="binance-futures",
        data_types=["trades"],
        from_date="2024-01-01",
        to_date="2024-01-02",
        symbols=["LTCUSDT"],
        download_dir="data/tardis_test",
    )


if __name__ == "__main__":
    asyncio.run(test_download())
