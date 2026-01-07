from enum import Enum

from core.interfaces import TimeIterator


class NetworkStatus(Enum):
    STOPPED = 0
    STARTING = 1
    CONNECTED = 2
    NOT_CONNECTED = 3
    ERROR = 4


class NetworkIterator(TimeIterator):
    """
    A TimeIterator that also maintains a NetworkStatus state.
    Base class for ExchangeAdapters and Connectors in V4.
    """

    def __init__(self):
        super().__init__()
        self._network_status = NetworkStatus.STOPPED

    @property
    def network_status(self) -> NetworkStatus:
        return self._network_status

    @property
    def ready(self) -> bool:
        """Returns True if the component is fully operational."""
        return self._network_status == NetworkStatus.CONNECTED

    async def check_network(self) -> NetworkStatus:
        """
        Force a check of the network status.
        Should be implemented by subclasses.
        """
        raise NotImplementedError
