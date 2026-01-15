import asyncio
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from core.interfaces import TimeIterator

logger = logging.getLogger("Watchdog")


@dataclass
class WatchedTask:
    name: str
    timeout: float
    last_heartbeat: float
    last_message: Optional[str] = None
    recovery_callback: Optional[Callable[[], Any]] = None
    is_critical: bool = True


class WatchdogRegistry(TimeIterator):
    """
    Registry for monitoring the health of internal bot tasks.
    Allows components to register their loops and report heartbeats.
    If a component stops reporting heartbeats for longer than its timeout,
    an alert or recovery action is triggered.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WatchdogRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self.tasks: Dict[str, WatchedTask] = {}
        self.running = False
        self._initialized = True
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def register(
        self, name: str, timeout: float = 60.0, recovery_callback: Optional[Callable] = None, is_critical: bool = True
    ):
        """Register a new task to be monitored."""
        self.tasks[name] = WatchedTask(
            name=name,
            timeout=timeout,
            last_heartbeat=time.time(),
            recovery_callback=recovery_callback,
            is_critical=is_critical,
        )
        logger.info(f"🛡️ Task registered: {name} (Timeout: {timeout}s, Critical: {is_critical})")

    def heartbeat(self, name: str, message: Optional[str] = None):
        """Report a heartbeat for a registered task."""
        if name in self.tasks:
            self.tasks[name].last_heartbeat = time.time()
            self.tasks[name].last_message = message
        else:
            # Auto-register with default settings if it hasn't been registered yet
            self.register(name)

    def unregister(self, name: str):
        """Unregister a monitored task."""
        if name in self.tasks:
            del self.tasks[name]
        # Silent if not found (idempotent)

    @property
    def name(self) -> str:
        return "Watchdog"

    async def start(self):
        """Start the watchdog monitor."""
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="WatchdogMonitor")
        self._monitor_thread.start()
        logger.info("🛡️ Watchdog monitor started (Independent thread).")

    async def stop(self):
        """Stop the watchdog monitor."""
        self.running = False
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)
        logger.info("🛡️ Watchdog monitor stopped.")

    async def tick(self, timestamp: float) -> None:
        """
        Clock-driven tick.
        In thread mode, this simply reports that the Clock is alive.
        """
        self.heartbeat("clock_reactor", "Clock loop active")

    def _monitor_loop(self):
        """
        Background loop running in a separate thread.
        Monitors health of all registered tasks independently of the event loop.
        """
        # Register the clock reactor itself for monitoring
        self.register("clock_reactor", timeout=10.0, is_critical=True)

        while not self._stop_event.is_set():
            try:
                now = time.time()
                for name, task in list(self.tasks.items()):
                    elapsed = now - task.last_heartbeat
                    if elapsed > task.timeout:
                        msg = f"🚨 TASK STALL DETECTED: {name} | Last heartbeat: {elapsed:.2f}s ago"
                        if task.last_message:
                            msg += f" | Last message: '{task.last_message}'"

                        logger.error(msg)
                        if task.recovery_callback:
                            try:
                                logger.warning(f"🔄 Triggering recovery callback for {name}...")
                                # Note: Asynchronous callbacks might not run if the loop is dead
                                if asyncio.iscoroutinefunction(task.recovery_callback):
                                    logger.warning(
                                        f"⚠️ Cannot execute coroutine callback for {name} from Watchdog thread if loop is hung!"
                                    )
                                else:
                                    task.recovery_callback()
                            except Exception as e:
                                logger.error(f"❌ Recovery callback failed for {name}: {e}")

                        # Reset heartbeat to avoid alert storm
                        task.last_heartbeat = now
            except Exception as e:
                # Log to stderr directly if logger is also hung (unlikely but safe)
                print(f"❌ Critical error in Watchdog thread: {e}", file=sys.stderr)

            time.sleep(2.0)

    def get_status(self) -> Dict[str, Any]:
        """Return a report of all monitored tasks."""
        now = time.time()
        return {
            name: {
                "elapsed": now - task.last_heartbeat,
                "timeout": task.timeout,
                "healthy": (now - task.last_heartbeat) < task.timeout,
                "last_message": task.last_message,
            }
            for name, task in self.tasks.items()
        }


# Global instance
watchdog = WatchdogRegistry()
