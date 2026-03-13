import math
from collections import deque


class RollingZScore:
    """
    O(1) sliding window tracking for Mean, Variance, and Z-Score calculations.
    Used by Footprint and Advanced sensors to replace static multipliers with probabilistic regimes.
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        self.sum = 0.0
        self.sum_sq = 0.0

    def update(self, value: float):
        if len(self.history) == self.window_size:
            old_val = self.history.popleft()
            self.sum -= old_val
            self.sum_sq -= old_val * old_val

            # Prevent floating point precision drift explicitly going negative
            if self.sum_sq < 0:
                self.sum_sq = 0.0

        self.history.append(value)
        self.sum += value
        self.sum_sq += value * value

    def get_zscore(self, value: float) -> float:
        n = len(self.history)
        if n < 2:
            return 0.0

        mean = self.sum / n
        # variance = E[X^2] - (E[X])^2
        variance = (self.sum_sq / n) - (mean * mean)

        if variance <= 0:
            return 0.0

        std = math.sqrt(variance)
        return (value - mean) / std

    @property
    def mean(self) -> float:
        n = len(self.history)
        return self.sum / n if n > 0 else 0.0

    @property
    def is_ready(self) -> bool:
        """Returns True if enough history has accumulated to be statistically relevant."""
        return len(self.history) >= min(10, self.window_size // 2)
