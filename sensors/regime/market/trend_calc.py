import logging
from collections import deque
from typing import Optional

from sensors.quant.volatility_regime import RollingZScore

logger = logging.getLogger("MarketRegimeSensor.Trend")

# Layer 1 — Micro: tick-level flow momentum
MICRO_FLOW_WINDOW_SECONDS = 10.0  # Rolling window for delta accumulation
MICRO_SURGE_Z_THRESHOLD = 1.2  # Z-score to declare directional flow surge (aligned price+delta)
MICRO_ABSORPTION_Z_THRESHOLD = 1.8  # Higher threshold for absorption (spoofing protection, VOLATIL_BAJO_FLOW)
MICRO_SNAPSHOT_HZ = 4.0  # Snapshots per second

# Layer 2 — Meso: VA expansion rate
MESO_VA_EXPANSION_FAST_WINDOW = 3  # Candles for fast VA width measurement
MESO_VA_EXPANSION_SLOW_WINDOW = 10  # Candles for slow VA width measurement
MESO_EXPANSION_THRESHOLD = 0.05  # 5% faster expansion
MESO_IB_BREAK_WEIGHT = 0.4  # Extra weight if IB is broken with volume

# Layer 3 — Macro: POC migration velocity
MACRO_POC_HISTORY_WINDOW = 20  # Candles to measure POC velocity
MACRO_POC_VELOCITY_THRESHOLD = 0.0001  # 0.01% per candle
MACRO_CONSECUTIVE_MIGRATION = 3  # N consecutive candles migrating = conviction


class _MicroLayer:
    """
    Layer 1: Tick-level flow momentum detector.

    Measures the velocity and acceleration of the Cumulative Volume Delta
    over a short rolling window. Detects when aggressive flow is building
    in one direction before it shows up in candles.

    Key insight: A trend starts with aggressive flow, not with candle patterns.
    By the time candles show OTF, the flow has been building for 30-60 seconds.
    """

    def __init__(self):
        self.snapshot_interval = 1.0 / MICRO_SNAPSHOT_HZ
        self.window = MICRO_FLOW_WINDOW_SECONDS

        # (timestamp, price, cumulative_delta)
        self.history: deque = deque(maxlen=int(self.window * MICRO_SNAPSHOT_HZ) + 2)
        self.current_cvd = 0.0
        self._last_snapshot_ts = 0.0

        # Rolling Z-score of delta velocity to normalize across symbols
        self.delta_vel_zscore = RollingZScore(window_size=200)
        self.price_vel_zscore = RollingZScore(window_size=200)

        # Absorption persistence counter: requires 2+ consecutive snapshots
        # to declare absorption (prevents single-tick spoofing from triggering reversals)
        self._absorption_snapshots = 0

    def on_tick(self, price: float, qty: float, is_buyer_maker: bool, ts: float):
        """Update CVD on every tick."""
        if is_buyer_maker:
            self.current_cvd -= qty  # Seller was aggressive
        else:
            self.current_cvd += qty  # Buyer was aggressive

        if ts - self._last_snapshot_ts >= self.snapshot_interval:
            self.history.append((ts, price, self.current_cvd))
            self._last_snapshot_ts = ts

    def evaluate(self) -> dict:
        """
        Returns micro-layer vote.

        Logic:
        1. Calculate delta velocity over the last N seconds.
        2. Calculate price velocity over the same window.
        3. If both are aligned and delta velocity Z > threshold → directional surge.
        4. If delta velocity is high but price velocity is low → absorption (balance signal).
        """
        if len(self.history) < 4:
            return {"vote": "NEUTRAL", "score": 0.0, "reason": "insufficient_data"}

        now_ts, now_price, now_cvd = self.history[-1]

        # Find snapshot ~MICRO_FLOW_WINDOW_SECONDS ago
        cutoff = now_ts - self.window
        old_entry = self.history[0]
        for entry in self.history:
            if entry[0] >= cutoff:
                old_entry = entry
                break

        dt = now_ts - old_entry[0]
        if dt < 0.5:
            return {"vote": "NEUTRAL", "score": 0.0, "reason": "window_too_small"}

        delta_vel = (now_cvd - old_entry[2]) / dt  # contracts/second
        price_vel = (now_price - old_entry[1]) / old_entry[1] / dt  # %/second

        # Update Z-score normalizers
        self.delta_vel_zscore.update(abs(delta_vel))
        self.price_vel_zscore.update(abs(price_vel))

        dv_z = self.delta_vel_zscore.get_zscore(abs(delta_vel))
        pv_z = self.price_vel_zscore.get_zscore(abs(price_vel))

        # Case 1: Aligned surge — both delta and price moving same direction fast
        if dv_z > MICRO_SURGE_Z_THRESHOLD and pv_z > 1.0:
            direction = "UP" if delta_vel > 0 else "DOWN"
            score = min(1.0, (dv_z / 4.0) * 0.7 + (pv_z / 3.0) * 0.3)
            return {
                "vote": direction,
                "score": round(score, 3),
                "reason": "aligned_surge",
                "delta_vel": round(delta_vel, 2),
                "dv_z": round(dv_z, 2),
            }

        # Case 2: High delta velocity but price not moving → absorption
        # Direction is OPPOSITE to CVD: buyers absorbed (CVD up, price flat) → reversal DOWN
        # sellers absorbed (CVD down, price flat) → reversal UP
        # Uses higher Z threshold (1.8 vs 1.2) to filter spoofing in thin books (VOLATIL_BAJO_FLOW)
        if dv_z > MICRO_ABSORPTION_Z_THRESHOLD and pv_z < 1.0:
            self._absorption_snapshots += 1
            direction = "DOWN" if delta_vel > 0 else "UP"  # opposite of aggressive flow
            score = min(0.8, dv_z / 4.0)  # proportional to delta strength, capped below surge

            if self._absorption_snapshots >= 2:
                # Confirmed: 2+ consecutive snapshots showing absorption → genuine reversal setup
                return {
                    "vote": direction,
                    "score": round(score, 3),
                    "reason": "absorption_detected",
                    "delta_vel": round(delta_vel, 2),
                    "dv_z": round(dv_z, 2),
                }

            # First snapshot: potential absorption, not yet confirmed
            # Return NEUTRAL with low score to avoid triggering reversal on noise
            return {
                "vote": "NEUTRAL",
                "score": round(score * 0.3, 3),
                "reason": "absorption_candidate",
                "delta_vel": round(delta_vel, 2),
                "dv_z": round(dv_z, 2),
            }

        # Case 3: Weak or neutral flow
        self._absorption_snapshots = 0  # Reset absorption counter
        return {
            "vote": "NEUTRAL",
            "score": 0.0,
            "reason": "weak_flow",
            "delta_vel": round(delta_vel, 2),
            "dv_z": round(dv_z, 2),
        }


class _MesoLayer:
    """
    Layer 2: VA expansion rate detector.

    Measures how fast the Value Area is expanding relative to its recent
    average. A rapidly expanding VA means the market is leaving balance —
    it's accepting prices in new territory.

    Key insight: Before a trend is visible in price, the VA starts expanding.
    The market is "discovering" new value. This is the earliest structural
    signal of a regime change.

    Also monitors IB breaks: if price breaks the Initial Balance with
    significant volume, that's a strong trend signal.
    """

    def __init__(self):
        # VA width history: (timestamp, va_width_pct)
        self.va_width_history: deque = deque(maxlen=MESO_VA_EXPANSION_SLOW_WINDOW + 2)
        # IB break tracking
        self.ib_break_direction: Optional[str] = None
        self.ib_break_ts: float = 0.0
        self.ib_break_decay = 120.0  # IB break signal decays after 2 minutes

        # Latest VA extremes for directional expansion detection
        self._latest_val: float = 0.0
        self._latest_vah: float = 0.0
        self._latest_close: float = 0.0

    def on_candle(
        self,
        poc: float,
        vah: float,
        val: float,
        ib_high: Optional[float],
        ib_low: Optional[float],
        close: float,
        volume: float,
        avg_volume: float,
        ts: float,
    ):
        """Update on each new candle with current VA levels."""
        if poc <= 0 or vah <= 0 or val <= 0:
            return

        self._latest_vah = vah
        self._latest_val = val
        self._latest_close = close

        va_width_pct = (vah - val) / poc if poc > 0 else 0.0
        self.va_width_history.append((ts, va_width_pct))

        # Detect IB break with volume confirmation
        if ib_high and ib_low and ib_high > ib_low:
            vol_ratio = volume / avg_volume if avg_volume > 0 else 1.0
            if close > ib_high and vol_ratio > 1.2:
                self.ib_break_direction = "UP"
                self.ib_break_ts = ts
            elif close < ib_low and vol_ratio > 1.2:
                self.ib_break_direction = "DOWN"
                self.ib_break_ts = ts

    def evaluate(self, now_ts: float) -> dict:
        """
        Returns meso-layer vote.

        Logic:
        1. Compare fast VA width (last N candles) vs slow VA width (last M candles).
        2. If fast > slow by threshold → VA is expanding → market leaving balance.
        3. Direction is determined by where price is relative to VA center.
        4. IB break adds conviction weight.
        """
        if len(self.va_width_history) < MESO_VA_EXPANSION_FAST_WINDOW + 1:
            return {"vote": "NEUTRAL", "score": 0.0, "reason": "insufficient_data"}

        history = list(self.va_width_history)

        # Fast average (recent candles)
        fast_entries = history[-MESO_VA_EXPANSION_FAST_WINDOW:]
        fast_avg = sum(e[1] for e in fast_entries) / len(fast_entries)

        # Slow average (all available)
        slow_avg = sum(e[1] for e in history) / len(history)

        if slow_avg <= 0:
            return {"vote": "NEUTRAL", "score": 0.0, "reason": "zero_va_width"}

        expansion_rate = (fast_avg - slow_avg) / slow_avg  # Positive = expanding

        # Check IB break signal (decays over time)
        ib_vote = "NEUTRAL"
        ib_score = 0.0
        if self.ib_break_direction and (now_ts - self.ib_break_ts) < self.ib_break_decay:
            ib_vote = self.ib_break_direction
            # Score decays linearly
            ib_score = MESO_IB_BREAK_WEIGHT * (1.0 - (now_ts - self.ib_break_ts) / self.ib_break_decay)

        if expansion_rate > MESO_EXPANSION_THRESHOLD:
            # VA is expanding — market leaving balance
            # Direction determined by close position within the expanding VA:
            #   close near VAH (>75th percentile) + VA expanding → UP expansion
            #   close near VAL (<25th percentile) + VA expanding → DOWN expansion
            #   close in middle → ambiguous (use IB break or NEUTRAL)
            direction = "NEUTRAL"
            if self._latest_vah > self._latest_val:
                va_width = self._latest_vah - self._latest_val
                va_bias = (self._latest_close - self._latest_val) / va_width  # 0.0=VAL, 1.0=VAH
                if va_bias > 0.75:
                    direction = ib_vote if ib_vote != "NEUTRAL" else "UP"
                elif va_bias < 0.25:
                    direction = ib_vote if ib_vote != "NEUTRAL" else "DOWN"

            if direction == "NEUTRAL" and ib_vote != "NEUTRAL":
                direction = ib_vote

            base_score = min(0.6, expansion_rate / (MESO_EXPANSION_THRESHOLD * 3))
            total_score = min(1.0, base_score + ib_score)
            return {
                "vote": direction,
                "score": round(total_score, 3),
                "reason": "va_expanding",
                "expansion_rate": round(expansion_rate, 4),
                "ib_break": ib_vote,
            }

        if expansion_rate < -0.05:
            # VA is contracting — market returning to balance
            return {
                "vote": "NEUTRAL",
                "score": 0.0,
                "reason": "va_contracting",
                "expansion_rate": round(expansion_rate, 4),
            }

        # Stable VA — balance
        return {
            "vote": "NEUTRAL",
            "score": 0.0,
            "reason": "va_stable",
            "expansion_rate": round(expansion_rate, 4),
        }


class _MacroLayer:
    """
    Layer 3: POC migration velocity detector.

    Measures the speed and consistency of POC migration. A POC that moves
    consistently in one direction means the market is accepting new value —
    it's not a temporary excursion, it's a structural shift.

    Key insight: POC migration is the most reliable leading indicator of
    a sustained trend. It's slower than flow (Layer 1) but more reliable.
    When all 3 layers agree, the regime change is real.
    """

    def __init__(self):
        # (timestamp, poc_price)
        self.poc_history: deque = deque(maxlen=MACRO_POC_HISTORY_WINDOW + 2)
        self.candle_count = 0

    def on_candle(self, poc: float, ts: float):
        """Update on each new candle."""
        if poc > 0:
            self.poc_history.append((ts, poc))
            self.candle_count += 1

    def evaluate(self) -> dict:
        """
        Returns macro-layer vote.

        Logic:
        1. Calculate POC velocity (% change per candle) over the window.
        2. Count consecutive candles where POC moved in the same direction.
        3. If velocity > threshold AND consecutive count > N → trend conviction.
        """
        if len(self.poc_history) < MACRO_CONSECUTIVE_MIGRATION + 1:
            return {"vote": "NEUTRAL", "score": 0.0, "reason": "insufficient_data"}

        history = list(self.poc_history)

        # Overall velocity over the full window
        start_poc = history[0][1]
        end_poc = history[-1][1]
        n_candles = len(history) - 1
        if start_poc <= 0 or n_candles <= 0:
            return {"vote": "NEUTRAL", "score": 0.0, "reason": "invalid_poc"}

        total_migration = (end_poc - start_poc) / start_poc
        velocity_per_candle = total_migration / n_candles  # signed %/candle

        # Count net direction ratio (robust to choppy markets)
        # Instead of consecutive candles that reset on any opposite move,
        # count what fraction of candles move in the dominant direction
        ups = 0
        downs = 0
        for i in range(1, len(history)):
            if history[i][1] > history[i - 1][1]:
                ups += 1
            elif history[i][1] < history[i - 1][1]:
                downs += 1
        total_moves = ups + downs
        direction = "UP" if ups > downs else "DOWN"
        dominant_count = ups if direction == "UP" else downs
        # net_ratio: 0.50 = balanced, 1.00 = all candles in one direction
        net_ratio = dominant_count / max(1, total_moves)
        has_direction = net_ratio > 0.55  # >55% candles agree on direction

        # Score: combination of velocity magnitude and directional conviction
        vel_score = min(0.5, abs(velocity_per_candle) / (MACRO_POC_VELOCITY_THRESHOLD * 4))
        # Map net_ratio 0.55→0.0 to 0.80→0.5 (linear)
        direction_score = min(0.5, max(0.0, (net_ratio - 0.55) / 0.50))
        total_score = vel_score + direction_score

        if abs(velocity_per_candle) > MACRO_POC_VELOCITY_THRESHOLD and has_direction:
            return {
                "vote": direction,
                "score": round(total_score, 3),
                "reason": "poc_migration_conviction",
                "velocity_per_candle": round(velocity_per_candle * 100, 5),
                "net_ratio": round(net_ratio, 3),
            }

        if abs(velocity_per_candle) > MACRO_POC_VELOCITY_THRESHOLD:
            # Velocity present but not enough directional conviction — early signal
            return {
                "vote": direction,
                "score": round(total_score * 0.5, 3),
                "reason": "poc_migration_early",
                "velocity_per_candle": round(velocity_per_candle * 100, 5),
                "net_ratio": round(net_ratio, 3),
            }

        return {
            "vote": "NEUTRAL",
            "score": 0.0,
            "reason": "poc_stable",
            "velocity_per_candle": round(velocity_per_candle * 100, 5),
        }
