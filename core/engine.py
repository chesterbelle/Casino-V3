"""
Core Engine for Casino-V3.
Handles the main event loop, component lifecycle, and event dispatching.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List

try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from core.observability.watchdog import watchdog

from .events import Event, EventType

logger = logging.getLogger(__name__)


class Engine:
    """Core event processing engine for Casino-V3.

    The Engine manages the application lifecycle and coordinates event-driven
    communication between components. It provides:
    - Event subscription and dispatching
    - Component lifecycle management (start/stop)
    - Strategy coordination
    - Data feed management

    Architecture:
        The Engine uses an event bus pattern where components subscribe to
        specific event types and receive callbacks when those events occur.
        All callbacks are executed concurrently using asyncio.gather().

    Example:
        >>> engine = Engine()
        >>> engine.data_feed = stream_manager
        >>> engine.strategies = [adaptive_player]
        >>>
        >>> # Subscribe to market events
        >>> async def on_tick(event):
        ...     print(f"Received tick: {event.data}")
        >>> engine.subscribe(EventType.TICK, on_tick)
        >>>
        >>> # Start engine (blocks until stopped)
        >>> await engine.start()

    Note:
        The Engine does NOT create its own event loop. It uses the current
        running loop via asyncio functions.
    """

    def __init__(self):
        """Initialize the Engine with empty component registries.

        Sets up:
            - Event subscriber dictionary (EventType -> List[Callback])
            - Empty strategies list
            - Null data_feed and order_manager (set by main.py)
            - running flag = False
        """
        self.running = False

        # Event Bus: Map EventType -> List[Callback]
        self._subscribers: Dict[EventType, List[Callable[[Event], Awaitable[None]]]] = {}

        # Components
        self.strategies = []
        self.data_feed = None
        self.order_manager = None

    def subscribe(self, event_type: EventType, callback: Callable[[Event], Awaitable[None]]):
        """Subscribe a callback to an event type.

        Args:
            event_type: The type of event to listen for (e.g., EventType.TICK)
            callback: Async function that receives Event and returns None
                     Signature: async def callback(event: Event) -> None

        Example:
            >>> async def handle_decision(event: Event):
            ...     symbol = event.data["symbol"]
            ...     signal = event.data["signal"]
            ...     print(f"Decision: {signal} on {symbol}")
            >>>
            >>> engine.subscribe(EventType.DECISION, handle_decision)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    async def dispatch(self, event: Event):
        """Dispatch an event to all subscribers concurrently.

        All callbacks for the event type are executed in parallel using
        asyncio.gather(). Exceptions in callbacks are caught and logged
        but don't prevent other callbacks from executing.

        Args:
            event: Event instance to dispatch

        Note:
            - Callbacks execute concurrently (not sequentially)
            - Errors in one callback don't affect others
            - Watchdog heartbeat is signaled on each dispatch
        """
        # Report heartbeat on event dispatch
        watchdog.heartbeat("engine_dispatch", f"Processing {event.type.name}")

        if event.type in self._subscribers:
            # Execute all callbacks concurrently
            callbacks = self._subscribers[event.type]
            results = await asyncio.gather(*(cb(event) for cb in callbacks), return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"❌ Error in event handler: {res}", exc_info=res)

    async def start(self, blocking: bool = True):
        """Start the engine and all components."""
        logger.info("🚀 Starting Casino-V3 Engine...")
        self.running = True

        # Start Data Feed
        if self.data_feed:
            await self.data_feed.connect()

        # Start Strategies
        for strategy in self.strategies:
            if hasattr(strategy, "on_start"):
                await strategy.on_start()

        logger.info("✅ Engine running. Waiting for events...")

        if blocking:
            # Keep the loop alive
            while self.running:
                await asyncio.sleep(0.1)

            await self.stop()

    async def stop(self):
        """Stop the engine and cleanup."""
        logger.info("🛑 Stopping Engine...")
        self.running = False

        # Stop Strategies
        for strategy in self.strategies:
            if hasattr(strategy, "on_stop"):
                await strategy.on_stop()

        # CRITICAL: DO NOT disconnect data_feed here!
        # The connector must remain alive for emergency_sweep to close positions.
        # The connector will be disconnected later in main.py shutdown sequence.
        # if self.data_feed:
        #     await self.data_feed.disconnect()

        logger.info("👋 Engine stopped.")

        # Cancel all running tasks (except current)
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()

        # Wait for tasks to cancel
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def run(self):
        """Entry point to run the engine (blocking)."""
        # Legacy method if not using asyncio.run
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            pass
