import asyncio

import pytest

from core.clock import Clock
from core.interfaces import TimeIterator


class MockIterator(TimeIterator):
    def __init__(self, name="Mock"):
        self._name = name
        self.tick_count = 0
        self.last_timestamp = 0

    @property
    def name(self) -> str:
        return self._name

    async def tick(self, timestamp: float) -> None:
        self.tick_count += 1
        self.last_timestamp = timestamp

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


@pytest.mark.asyncio
async def test_clock_ticking():
    clock = Clock(tick_size_seconds=0.1)  # Fast tick for testing
    iterator = MockIterator()
    clock.add_iterator(iterator)

    await clock.start()

    # Let it run for 0.35s (Should get roughly 3-4 ticks depending on alignment)
    await asyncio.sleep(0.35)

    await clock.stop()

    assert iterator.tick_count >= 3
    assert iterator.last_timestamp > 0


@pytest.mark.asyncio
async def test_clock_error_isolation():
    """Ensure one failing child doesn't stop the clock."""

    class FailingIterator(TimeIterator):
        @property
        def name(self):
            return "Failer"

        async def tick(self, ts):
            raise ValueError("Crash!")

        async def start(self):
            pass

        async def stop(self):
            pass

    clock = Clock(tick_size_seconds=0.1)
    failer = FailingIterator()
    good = MockIterator("Good")

    clock.add_iterator(failer)
    clock.add_iterator(good)

    await clock.start()
    await asyncio.sleep(0.35)
    await clock.stop()

    assert good.tick_count >= 3  # The good one should still receive ticks
