from collections import defaultdict, deque
from typing import Dict, Tuple

# Try to use sortedcontainers for O(log n) insert + O(1) index
try:
    from sortedcontainers import SortedList

    _HAS_SORTEDLIST = True
except ImportError:
    _HAS_SORTEDLIST = False


class MarketProfile:
    """
    Market Profile & Volume Profile tracker.
    Implements James Dalton's Market Profile concepts (Value Area, POC).
    Calculates the area where 70% of volume/TPOs occurred.

    Uses a rolling time window (default 8h) so the profile always reflects
    recent price action. Ticks older than the window are automatically pruned,
    preventing VA range expansion drift without needing hard resets or decay.
    """

    def __init__(self, tick_size: float, value_area_pct: float = 0.70, rolling_window: float = 28800):
        self.tick_size = tick_size
        self.value_area_pct = value_area_pct
        self.rolling_window = rolling_window  # seconds, 0 = unlimited
        self.profile: Dict[float, float] = defaultdict(float)  # price_level -> volume
        self.total_volume = 0.0
        self.poc_history = deque(maxlen=300)  # Phase 1150: Track POC migration
        # O(1) running POC tracking
        self._poc_price = 0.0
        self._poc_volume = 0.0
        self._last_logged_poc = 0.0
        # Sorted price levels for O(log n) lookup in calculate_value_area
        self._sorted_prices = SortedList() if _HAS_SORTEDLIST else None
        # Rolling window tick log (timestamp, price_level, volume)
        self._tick_log: deque = deque()

    def round_price(self, price: float) -> float:
        """Rounds price to the nearest tick size."""
        if self.tick_size <= 0:
            return price
        # Use round(price / tick) * tick to snap to grid
        return round(price / self.tick_size) * self.tick_size

    def add_trade(self, price: float, volume: float, timestamp: float = None):
        """Processes a new trade/tick and adds it to the profile.
        If timestamp is provided and rolling_window > 0, old ticks outside
        the window are automatically pruned.
        """
        if volume <= 0:
            return

        level = self.round_price(price)
        is_new_level = level not in self.profile
        self.profile[level] += volume
        self.total_volume += volume

        if self._sorted_prices is not None and is_new_level:
            self._sorted_prices.add(level)

        # Rolling window: track this tick and prune expired ones
        if self.rolling_window > 0 and timestamp is not None:
            self._tick_log.append((timestamp, level, volume))
            cutoff = timestamp - self.rolling_window
            while self._tick_log and self._tick_log[0][0] < cutoff:
                old_ts, old_level, old_vol = self._tick_log.popleft()
                self.profile[old_level] -= old_vol
                self.total_volume -= old_vol
                if self.profile[old_level] <= 0:
                    del self.profile[old_level]
                    if self._sorted_prices is not None and old_level in self._sorted_prices:
                        self._sorted_prices.remove(old_level)
                if old_level == self._poc_price:
                    self._recalculate_poc()

        # O(1) POC update: only recalculate if this level is now the max
        level_vol = self.profile[level]
        if level_vol > self._poc_volume:
            self._poc_price = level
            self._poc_volume = level_vol
        if self._poc_price != self._last_logged_poc:
            self.poc_history.append(self._poc_price)
            self._last_logged_poc = self._poc_price

    def calculate_value_area(self) -> Tuple[float, float, float]:
        """
        Calculates POC (Point of Control), VAH (Value Area High), and VAL (Value Area Low).
        Using the standard 70% value area rule.
        Returns: (POC, VAH, VAL)
        """
        if not self.profile:
            return 0.0, 0.0, 0.0

        # 1. Find the Point of Control (POC) - use O(1) running max
        poc = self._poc_price

        # 2. Determine target volume for Value Area (70%)
        target_volume = self.total_volume * self.value_area_pct
        current_volume = self.profile[poc]

        # 3. Expand Value Area up and down until target volume is reached
        if self._sorted_prices is not None:
            # O(log n) lookup using SortedList
            sorted_prices = self._sorted_prices
            poc_idx = sorted_prices.index(poc)
        else:
            # Fallback: O(n log n) sort
            sorted_prices = sorted(self.profile.keys())
            poc_idx = sorted_prices.index(poc)

        up_idx = poc_idx + 1
        down_idx = poc_idx - 1

        vah = poc
        val = poc

        while current_volume < target_volume:
            # Check edge cases (reached top or bottom)
            if up_idx >= len(sorted_prices) and down_idx < 0:
                break

            vol_up_1 = self.profile[sorted_prices[up_idx]] if up_idx < len(sorted_prices) else 0
            vol_up_2 = self.profile[sorted_prices[up_idx + 1]] if up_idx + 1 < len(sorted_prices) else 0
            total_up = vol_up_1 + vol_up_2

            vol_down_1 = self.profile[sorted_prices[down_idx]] if down_idx >= 0 else 0
            vol_down_2 = self.profile[sorted_prices[down_idx - 1]] if down_idx - 1 >= 0 else 0
            total_down = vol_down_1 + vol_down_2

            # Determine which side (up or down) has more volume to expand into
            if total_up >= total_down and total_up > 0:
                # Expand Up
                current_volume += vol_up_1
                vah = sorted_prices[up_idx]
                up_idx += 1
                if current_volume < target_volume and up_idx < len(sorted_prices):
                    current_volume += vol_up_2
                    vah = sorted_prices[up_idx]
                    up_idx += 1
            elif total_down > total_up:
                # Expand Down
                current_volume += vol_down_1
                val = sorted_prices[down_idx]
                down_idx -= 1
                if current_volume < target_volume and down_idx >= 0:
                    current_volume += vol_down_2
                    val = sorted_prices[down_idx]
                    down_idx -= 1
            else:
                # Both sides exhausted (should not happen before total_volume edge case)
                break

        return poc, vah, val

    def get_cluster_density(self, price: float, range_ticks: int = 2) -> float:
        """
        Trader Dale's Volume Cluster Density.
        Calculates the relative density of volume around a specific price level
        compared to the average volume across the entire profile.
        Returns a ratio (e.g., 2.5 means 2.5x the average volume).
        """
        if not self.profile or self.total_volume == 0:
            return 0.0

        avg_vol_per_level = self.total_volume / len(self.profile)
        if avg_vol_per_level == 0:
            return 0.0

        level = self.round_price(price)
        sorted_prices = sorted(self.profile.keys())

        if level not in sorted_prices:
            return 0.0

        idx = sorted_prices.index(level)

        local_vol = 0.0
        levels_counted = 0

        start_idx = max(0, idx - range_ticks)
        end_idx = min(len(sorted_prices) - 1, idx + range_ticks)

        for i in range(start_idx, end_idx + 1):
            local_vol += self.profile[sorted_prices[i]]
            levels_counted += 1

        avg_local_vol = local_vol / levels_counted

        return avg_local_vol / avg_vol_per_level

    def calculate_va_integrity(self) -> float:
        """
        Phase 1150: Calculate Value Area Integrity Score (Axia style).
        Formula: (POC_volume / Total_volume) * (1 / VA_range_pct)

        A 'Clean' VA has a concentrated POC and tight range.
        An 'Unhealthy' VA is expanded and double-peaked.
        """
        if self.total_volume <= 0:
            return 0.0

        poc, vah, val = self.calculate_value_area()
        if vah <= val or poc <= 0.0:
            return 0.0

        poc_vol = self.profile.get(poc, 0.0)
        va_range_pct = (vah - val) / poc

        # Integrity = Concentration * Magnetism
        # Concentration: % of volume at POC
        # Magnetism: Inverse of range (tightness)
        concentration = poc_vol / self.total_volume
        magnetism = 1.0 / (va_range_pct * 100)  # Scale to match goal >= 0.25

        return concentration * magnetism

    def _recalculate_poc(self):
        """Full scan to find the current POC. Called when the POC level is pruned."""
        if not self.profile:
            self._poc_price = 0.0
            self._poc_volume = 0.0
            return
        self._poc_price = max(self.profile, key=self.profile.get)
        self._poc_volume = self.profile[self._poc_price]

    def reset(self):
        """Clears the profile for a new session/day."""
        self.profile.clear()
        self.total_volume = 0.0
        self._poc_price = 0.0
        self._poc_volume = 0.0
        self._last_logged_poc = 0.0
        self.poc_history.clear()
        self._tick_log.clear()
        if self._sorted_prices is not None:
            self._sorted_prices.clear()

    def decay(self, factor: float = 0.5):
        """
        Exponential decay of the profile instead of a hard reset.
        Scales all accumulated volume by `factor`, preserving ratios
        (POC concentration, VA range width) so va_integrity stays stable.
        Note: clears tick_log since timestamps would no longer match volumes.
        """
        if self.total_volume <= 0:
            return

        floor = 1e-12  # only prune truly dead levels
        for level in list(self.profile.keys()):
            new_vol = self.profile[level] * factor
            if new_vol <= floor:
                del self.profile[level]
            else:
                self.profile[level] = new_vol

        self.total_volume *= factor
        self._poc_volume *= factor
        self._tick_log.clear()

        # Rebuild sorted list from remaining levels
        if self._sorted_prices is not None:
            self._sorted_prices.clear()
            self._sorted_prices.update(self.profile.keys())
