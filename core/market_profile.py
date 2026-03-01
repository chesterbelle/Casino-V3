from collections import defaultdict
from typing import Dict, Tuple


class MarketProfile:
    """
    Market Profile & Volume Profile tracker.
    Implements James Dalton's Market Profile concepts (Value Area, POC).
    Calculates the area where 70% of volume/TPOs occurred.
    """

    def __init__(self, tick_size: float, value_area_pct: float = 0.70):
        self.tick_size = tick_size
        self.value_area_pct = value_area_pct
        self.profile: Dict[float, float] = defaultdict(float)  # price_level -> volume
        self.total_volume = 0.0

    def round_price(self, price: float) -> float:
        """Rounds price to the nearest tick size."""
        if self.tick_size <= 0:
            return price
        # Use round(price / tick) * tick to snap to grid
        return round(price / self.tick_size) * self.tick_size

    def add_trade(self, price: float, volume: float):
        """Processes a new trade/tick and adds it to the profile."""
        if volume <= 0:
            return

        level = self.round_price(price)
        self.profile[level] += volume
        self.total_volume += volume

    def calculate_value_area(self) -> Tuple[float, float, float]:
        """
        Calculates POC (Point of Control), VAH (Value Area High), and VAL (Value Area Low).
        Using the standard 70% value area rule.
        Returns: (POC, VAH, VAL)
        """
        if not self.profile:
            return 0.0, 0.0, 0.0

        # 1. Find the Point of Control (POC) - highest volume node
        poc = max(self.profile.items(), key=lambda x: x[1])[0]

        # 2. Determine target volume for Value Area (70%)
        target_volume = self.total_volume * self.value_area_pct
        current_volume = self.profile[poc]

        # 3. Expand Value Area up and down until target volume is reached
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

    def reset(self):
        """Clears the profile for a new session/day."""
        self.profile.clear()
        self.total_volume = 0.0
