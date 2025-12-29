"""
Sensor Performance Tracker for Casino-V3.

Tracks historical performance of each sensor to enable intelligent signal prioritization.
Replaces simple voting with data-driven decision making.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Configuration
STATE_FILE = Path("state/sensor_stats.json")
SHORT_WINDOW = 50  # Recent performance
MEDIUM_WINDOW = 200  # Medium-term performance
MIN_TRADES_FOR_SCORING = 10  # Minimum trades before trusting stats


@dataclass
class SensorStats:
    """Performance statistics for a single sensor."""

    sensor_id: str
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0

    # Profit metrics
    total_profit: float = 0.0
    total_loss: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    # Recent performance (deques stored as lists in JSON)
    recent_trades: list = None  # Last 200 trades (win/loss)
    recent_pnls: list = None  # Last 200 PnLs

    # Calculated metrics (cached)
    win_rate_short: float = 0.0
    win_rate_medium: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    current_streak: int = 0

    # Metadata
    last_updated: float = 0.0
    last_win_time: float = 0.0  # Timestamp of last winning trade

    def __post_init__(self):
        """Initialize deques if None."""
        if self.recent_trades is None:
            self.recent_trades = []
        if self.recent_pnls is None:
            self.recent_pnls = []


class SensorTracker:
    """
    Tracks performance metrics for all sensors.

    Provides intelligent scoring based on:
    - Expectancy (expected value per trade)
    - Win rates (short and medium term)
    - Profit factor (risk-adjusted returns)
    - Current streak (momentum)
    """

    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.sensors: Dict[str, SensorStats] = {}
        self._load_state()

        logger.info(f"✅ SensorTracker initialized | Sensors: {len(self.sensors)}")

    def update_sensor(self, sensor_id: str, pnl: float, won: bool) -> None:
        """
        Update sensor statistics after a trade closes.

        Args:
            sensor_id: Sensor that generated the signal
            pnl: Profit/Loss from the trade
            won: True if trade was profitable
        """
        # Get or create sensor stats
        if sensor_id not in self.sensors:
            self.sensors[sensor_id] = SensorStats(sensor_id=sensor_id)

        stats = self.sensors[sensor_id]

        # Update counters
        stats.total_trades += 1
        if won:
            stats.total_wins += 1
            stats.gross_profit += pnl
        else:
            stats.total_losses += 1
            stats.gross_loss += abs(pnl)

        # Update totals
        stats.total_profit += pnl if won else 0
        stats.total_loss += abs(pnl) if not won else 0

        # Update recent history (keep last MEDIUM_WINDOW)
        stats.recent_trades.append(1 if won else 0)
        stats.recent_pnls.append(pnl)

        if len(stats.recent_trades) > MEDIUM_WINDOW:
            stats.recent_trades.pop(0)
            stats.recent_pnls.pop(0)

        # Update streak and last win time
        if won:
            stats.current_streak = stats.current_streak + 1 if stats.current_streak > 0 else 1
            stats.last_win_time = time.time()  # Track recency
        else:
            stats.current_streak = stats.current_streak - 1 if stats.current_streak < 0 else -1

        # Recalculate metrics
        self._calculate_metrics(stats)

        # Update timestamp
        stats.last_updated = time.time()

        logger.debug(
            f"📊 Updated {sensor_id} | "
            f"Trades: {stats.total_trades} | "
            f"WR: {stats.win_rate_short:.1%} | "
            f"Exp: {stats.expectancy:.4f}"
        )

    def _calculate_metrics(self, stats: SensorStats) -> None:
        """Calculate derived metrics from raw data."""
        if stats.total_trades == 0:
            return

        # Win rates
        if len(stats.recent_trades) >= SHORT_WINDOW:
            stats.win_rate_short = sum(stats.recent_trades[-SHORT_WINDOW:]) / SHORT_WINDOW
        else:
            stats.win_rate_short = stats.total_wins / stats.total_trades

        stats.win_rate_medium = sum(stats.recent_trades) / len(stats.recent_trades) if stats.recent_trades else 0.0

        # Average win/loss
        if stats.total_wins > 0:
            stats.avg_win = stats.gross_profit / stats.total_wins
        if stats.total_losses > 0:
            stats.avg_loss = stats.gross_loss / stats.total_losses

        # Expectancy: (WR × AvgWin) - (LR × AvgLoss)
        loss_rate = stats.total_losses / stats.total_trades
        stats.expectancy = (stats.win_rate_medium * stats.avg_win) - (loss_rate * stats.avg_loss)

        # Profit Factor: GrossProfit / GrossLoss
        if stats.gross_loss > 0:
            stats.profit_factor = stats.gross_profit / stats.gross_loss
        else:
            stats.profit_factor = stats.gross_profit if stats.gross_profit > 0 else 0.0

    def get_sensor_score(self, sensor_id: str) -> float:
        """
        Calculate composite quality score for a sensor.

        Uses relative metrics to enable comparison between sensors.
        Score is normalized to 0-1 range where higher = better.

        Components:
        - Expectancy (40%): Expected value per trade
        - Profit Factor (25%): Risk-adjusted returns
        - Streak (20%): Recent winning/losing momentum
        - Win Rate (10%): Consistency
        - Time Decay (5%): Recency of success

        Returns:
            Score between 0.0 and 1.0 (higher is better)
            Returns 0.5 (neutral) for sensors with insufficient data
        """
        if sensor_id not in self.sensors:
            return 0.5  # Neutral score for unknown sensors

        stats = self.sensors[sensor_id]

        # Cold start: not enough data
        if stats.total_trades < MIN_TRADES_FOR_SCORING:
            return 0.5

        # Component 1: Win Rate (already 0-1)
        win_rate_score = stats.win_rate_short

        # Component 2: Expectancy (normalize around 0, typical range -0.01 to +0.01)
        # Shift to 0-1 range: 0 expectancy = 0.5, positive = >0.5, negative = <0.5
        expectancy_score = 0.5 + (stats.expectancy * 25.0)  # ±0.02 expectancy → 0-1 range
        expectancy_score = max(min(expectancy_score, 1.0), 0.0)

        # Component 3: Profit Factor (normalize, typical range 0.5-2.0)
        # PF = 1.0 is breakeven, >1.0 is profitable
        if stats.profit_factor >= 1.0:
            # Profitable: map 1.0-2.0 → 0.5-1.0
            pf_score = 0.5 + min((stats.profit_factor - 1.0) / 2.0, 0.5)
        else:
            # Losing: map 0.0-1.0 → 0.0-0.5
            pf_score = stats.profit_factor * 0.5

        # Component 4: Streak (bonus/penalty) - INCREASED WEIGHT
        # Winning streaks boost, losing streaks penalize significantly
        if stats.current_streak > 0:
            # Max bonus at 5-win streak (more aggressive)
            streak_score = 0.5 + min(stats.current_streak / 5.0, 0.5)
        elif stats.current_streak < 0:
            # Max penalty at 3-loss streak (sensor fatigue kicks in faster)
            streak_score = 0.5 - min(abs(stats.current_streak) / 3.0, 0.5)
        else:
            streak_score = 0.5  # Neutral

        # Component 5: Time Decay - Recent success matters more
        # Decay factor: 0.95^days since last win
        if stats.last_win_time > 0:
            days_since_win = (time.time() - stats.last_win_time) / 86400.0
            time_decay_score = 0.95 ** min(days_since_win, 30)  # Cap at 30 days
        else:
            time_decay_score = 0.5  # Neutral for no wins yet

        # Weighted composite score
        score = (
            expectancy_score * 0.40  # Expected value per trade (primary)
            + pf_score * 0.25  # Risk-adjusted returns
            + streak_score * 0.20  # Recent momentum (INCREASED from 0.05)
            + win_rate_score * 0.10  # Consistency
            + time_decay_score * 0.05  # Recency bonus
        )

        return max(min(score, 1.0), 0.0)  # Clamp to [0, 1]

    def get_stats(self, sensor_id: str) -> Optional[SensorStats]:
        """Get statistics for a specific sensor."""
        return self.sensors.get(sensor_id)

    def get_all_stats(self) -> Dict[str, SensorStats]:
        """Get all sensor statistics."""
        return self.sensors

    def _load_state(self) -> None:
        """Load sensor statistics from JSON file."""
        if not self.state_file.exists():
            logger.info("📂 No existing sensor stats found, starting fresh")
            return

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)

            for sensor_id, stats_dict in data.items():
                self.sensors[sensor_id] = SensorStats(**stats_dict)

            logger.info(f"✅ Loaded stats for {len(self.sensors)} sensors from {self.state_file}")
        except Exception as e:
            logger.error(f"❌ Failed to load sensor stats: {e}")

    def save_state(self) -> None:
        """Save sensor statistics to JSON file."""
        try:
            # Ensure directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict
            data = {sensor_id: asdict(stats) for sensor_id, stats in self.sensors.items()}

            # Save to file
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"💾 Saved stats for {len(self.sensors)} sensors to {self.state_file}")
        except Exception as e:
            logger.error(f"❌ Failed to save sensor stats: {e}")

    def get_top_sensors(self, n: int = 10) -> list:
        """
        Get top N sensors by score.

        Args:
            n: Number of top sensors to return

        Returns:
            List of (sensor_id, score) tuples, sorted by score descending
        """
        scored_sensors = [(sensor_id, self.get_sensor_score(sensor_id)) for sensor_id in self.sensors.keys()]

        return sorted(scored_sensors, key=lambda x: x[1], reverse=True)[:n]

    def get_kelly_fraction(self, sensor_id: str, max_fraction: float = 0.25) -> float:
        """
        Calculate Kelly Criterion bet fraction for a sensor.

        Kelly Formula: f = W - (L / R)
        Where:
            W = Win rate (probability of winning)
            L = Loss rate (1 - W)
            R = Win/Loss ratio (avg_win / avg_loss)

        Args:
            sensor_id: Sensor to calculate Kelly for
            max_fraction: Maximum fraction to return (safety cap)

        Returns:
            Kelly fraction between 0.0 and max_fraction
            Returns 0.01 (minimum) for sensors with insufficient data
        """
        stats = self.sensors.get(sensor_id)

        if not stats or stats.total_trades < MIN_TRADES_FOR_SCORING:
            # Not enough data - return minimum bet
            return 0.01

        # Calculate win rate
        win_rate = stats.total_wins / max(stats.total_trades, 1)
        loss_rate = 1 - win_rate

        # Calculate average win/loss ratio
        if stats.avg_loss == 0:
            # No losses yet - return minimum (don't be overconfident)
            return 0.01

        win_loss_ratio = abs(stats.avg_win / stats.avg_loss) if stats.avg_loss != 0 else 1.0

        # Kelly formula: f = W - (L / R)
        kelly = win_rate - (loss_rate / win_loss_ratio)

        # Apply safety constraints
        # 1. Never bet more than max_fraction (e.g., 25%)
        # 2. Never bet negative (would mean edge is negative)
        # 3. Apply fractional Kelly (0.5 by default for safety)
        FRACTIONAL_KELLY = 0.5  # Use half-Kelly for safety

        kelly_fraction = max(0.01, min(kelly * FRACTIONAL_KELLY, max_fraction))

        logger.debug(
            f"📊 Kelly for {sensor_id}: W={win_rate:.2%} R={win_loss_ratio:.2f} "
            f"raw={kelly:.3f} final={kelly_fraction:.3f}"
        )

        return kelly_fraction
