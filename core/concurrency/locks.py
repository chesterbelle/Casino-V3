"""
Concurrency Control with Async Locks.

Provides named locks for critical sections to prevent race conditions.

Author: Casino V3 Team
Version: 2.0.0
"""

import asyncio
import logging
import time
from typing import Dict, Optional


class NamedLock:
    """
    Named async lock with timeout and deadlock detection.

    Example:
        lock_manager = LockManager()

        # Acquire lock
        async with lock_manager.lock("position_BTC/USDT"):
            # Critical section - only one coroutine at a time
            await open_position(...)

        # Or manual acquire/release
        await lock_manager.acquire("balance", timeout=5.0)
        try:
            # Critical section
            balance -= amount
        finally:
            lock_manager.release("balance")
    """

    def __init__(self, name: str):
        self.name = name
        self._lock = asyncio.Lock()
        self._holder: Optional[str] = None
        self._acquired_at: Optional[float] = None
        self._wait_count = 0

    async def acquire(self, timeout: Optional[float] = None, holder: str = "unknown"):
        """
        Acquire lock with optional timeout.

        Args:
            timeout: Max seconds to wait (None = wait forever)
            holder: Identifier of lock holder (for debugging)

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        self._wait_count += 1

        try:
            if timeout:
                await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
            else:
                await self._lock.acquire()

            self._holder = holder
            self._acquired_at = time.time()

        except asyncio.TimeoutError:
            self._wait_count -= 1
            raise

    def release(self):
        """Release lock."""
        if self._lock.locked():
            self._lock.release()
            self._holder = None
            self._acquired_at = None
            self._wait_count = max(0, self._wait_count - 1)

    def is_locked(self) -> bool:
        """Check if lock is currently held."""
        return self._lock.locked()

    def get_stats(self) -> Dict[str, any]:
        """Get lock statistics."""
        return {
            "name": self.name,
            "locked": self.is_locked(),
            "holder": self._holder,
            "acquired_at": self._acquired_at,
            "held_duration": time.time() - self._acquired_at if self._acquired_at else 0,
            "wait_count": self._wait_count,
        }


class LockManager:
    """
    Manager for named locks.

    Provides centralized lock management with deadlock detection.

    Example:
        lock_mgr = LockManager()

        # Use context manager
        async with lock_mgr.lock("resource_1"):
            # Critical section

        # Get lock stats
        stats = lock_mgr.get_all_stats()
    """

    def __init__(self, deadlock_timeout: float = 30.0):
        """
        Initialize lock manager.

        Args:
            deadlock_timeout: Max time a lock can be held (seconds)
        """
        self.deadlock_timeout = deadlock_timeout
        self._locks: Dict[str, NamedLock] = {}
        self._lock_creation_lock = asyncio.Lock()
        self.logger = logging.getLogger("LockManager")

    async def _get_or_create_lock(self, name: str) -> NamedLock:
        """Get existing lock or create new one."""
        if name not in self._locks:
            async with self._lock_creation_lock:
                if name not in self._locks:
                    self._locks[name] = NamedLock(name)
        return self._locks[name]

    async def acquire(self, name: str, timeout: Optional[float] = None, holder: str = "unknown"):
        """
        Acquire named lock.

        Args:
            name: Lock name
            timeout: Max wait time (None = use deadlock_timeout)
            holder: Lock holder identifier

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        lock = await self._get_or_create_lock(name)
        effective_timeout = timeout if timeout is not None else self.deadlock_timeout

        try:
            await lock.acquire(timeout=effective_timeout, holder=holder)
            self.logger.debug(f"🔒 Lock acquired: {name} by {holder}")
        except asyncio.TimeoutError:
            self.logger.error(f"❌ Lock timeout: {name} (waited {effective_timeout}s, " f"holder: {lock._holder})")
            raise

    def release(self, name: str):
        """
        Release named lock.

        Args:
            name: Lock name
        """
        if name in self._locks:
            self._locks[name].release()
            self.logger.debug(f"🔓 Lock released: {name}")

    def lock(self, name: str, timeout: Optional[float] = None, holder: str = "unknown"):
        """
        Get lock context manager.

        Args:
            name: Lock name
            timeout: Max wait time
            holder: Lock holder identifier

        Returns:
            LockContext for use with 'async with'
        """
        return LockContext(self, name, timeout, holder)

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all locks."""
        return {name: lock.get_stats() for name, lock in self._locks.items()}

    def detect_deadlocks(self) -> list:
        """
        Detect potential deadlocks (locks held too long).

        Returns:
            List of lock names that may be deadlocked
        """
        deadlocks = []
        current_time = time.time()

        for name, lock in self._locks.items():
            if lock.is_locked() and lock._acquired_at:
                held_duration = current_time - lock._acquired_at
                if held_duration > self.deadlock_timeout:
                    deadlocks.append(
                        {
                            "name": name,
                            "holder": lock._holder,
                            "held_duration": held_duration,
                        }
                    )
                    self.logger.warning(
                        f"⚠️ Potential deadlock: {name} held by {lock._holder} " f"for {held_duration:.1f}s"
                    )

        return deadlocks


class LockContext:
    """Context manager for named locks."""

    def __init__(self, manager: LockManager, name: str, timeout: Optional[float], holder: str):
        self.manager = manager
        self.name = name
        self.timeout = timeout
        self.holder = holder

    async def __aenter__(self):
        await self.manager.acquire(self.name, self.timeout, self.holder)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.manager.release(self.name)
        return False


# Global lock manager instance
_global_lock_manager: Optional[LockManager] = None


def get_lock_manager() -> LockManager:
    """Get global lock manager instance."""
    global _global_lock_manager
    if _global_lock_manager is None:
        _global_lock_manager = LockManager()
    return _global_lock_manager
