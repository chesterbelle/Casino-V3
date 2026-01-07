from abc import ABC, abstractmethod


class TimeIterator(ABC):
    """
    Interface for components that need to respond to time ticks.
    Used by the central Clock to drive execution.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the component for logging/debugging."""
        pass

    @abstractmethod
    async def tick(self, timestamp: float) -> None:
        """
        Called exactly once per clock tick.

        Args:
            timestamp: The standardized timestamp of the current tick.
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the component (and its own internal tasks if any)."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the component."""
        pass
