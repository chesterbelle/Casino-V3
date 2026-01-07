import asyncio
import logging
import time
from typing import List

from core.interfaces import TimeIterator


class Clock:
    """
    The TimeHeart of the Reactor Architecture.

    - Ticks exactly once per second (configurable).
    - Aligns ticks to the start of the second (drift correction).
    - Drives all registered TimeIterators sequentially or in parallel.
    """

    def __init__(self, tick_size_seconds: float = 1.0):
        self.tick_size = tick_size_seconds
        self.logger = logging.getLogger("Clock")
        self._children: List[TimeIterator] = []
        self._started = False
        self._main_task: asyncio.Task = None

    def add_iterator(self, iterator: TimeIterator):
        """Register a component to receive ticks."""
        if iterator not in self._children:
            self._children.append(iterator)
            self.logger.info(f"➕ Registered reactor component: {iterator.name}")

    def remove_iterator(self, iterator: TimeIterator):
        if iterator in self._children:
            self._children.remove(iterator)

    async def start(self):
        """Start the clock loop."""
        if self._started:
            return

        self._started = True
        self.logger.info(f"🕒 Clock started (Tick size: {self.tick_size}s)")

        # Start all children
        for child in self._children:
            await child.start()

        self._main_task = asyncio.create_task(self._run())

    async def stop(self):
        """Stop the clock loop."""
        if not self._started:
            return

        self._started = False
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass

        # Stop all children
        for child in self._children:
            await child.stop()

        self.logger.info("🛑 Clock stopped")

    async def _run(self):
        """
        The main reactor loop.
        Calculates time to next tick to ensure alignment.
        """
        while self._started:
            try:
                current_time = time.time()

                # 1. Emit Ticks
                # We start the tick processing "now"
                await self._process_tick(current_time)

                # 2. Calculate Sleep for Drift Correction
                # Target: next second boundary
                # If tick_size is 1.0, and now is 123.4s, we want to wake up at 124.0s
                # Sleep = 1.0 - 0.4 = 0.6s
                now = time.time()
                sleep_duration = self.tick_size - (now % self.tick_size)

                # Safety for extremely slow processing
                if sleep_duration < 0:
                    sleep_duration = 0

                await asyncio.sleep(sleep_duration)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"💥 Fatal Clock Error: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Panic sleep to avoid spin loop

    async def _process_tick(self, timestamp: float):
        """Distribute tick to all children."""
        # TODO: Decide if we want gather (parallel) or sequential.
        # Hummingbot uses sequential to ensure deterministic order (Connector -> Strategy).
        # We will use Sequential for safety in V4.0.

        for child in self._children:
            try:
                await child.tick(timestamp)
            except Exception as e:
                # Do NOT let one child crash the clock
                self.logger.error(f"⚠️ Error in {child.name}.tick(): {e}", exc_info=True)
