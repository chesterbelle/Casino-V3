"""
Market Regime Sensor — Anticipatory Regime Detection
Phase 2100: Replaces OneTimeframing with a 3-layer conviction model.

Problem with OneTimeframing:
    Requires N consecutive bars to declare a trend. At 1m with lookback=5,
    that's a minimum 5-minute lag. By the time the system says BULL_OTF,
    the price has already moved and the bot has already tried to short VAH.

This sensor operates on 3 simultaneous time layers and detects regime
changes *while they are occurring*, not after they are confirmed.

Architecture:
    LAYER 1 — Micro  (ticks, 0-10s):  Is flow accelerating in one direction?
    LAYER 2 — Meso   (candles, 1-5m): Is the VA expanding or contracting?
    LAYER 3 — Macro  (structure, 15m+): Is the POC migrating with conviction?

    All 3 layers vote → Regime with confidence score 0.0 to 1.0

Regime States:
    BALANCE     → Reversion allowed. VA is tight, POC stable, flow neutral.
    TRANSITION  → Reversion BLOCKED. Market is choosing direction. Danger zone.
    TREND_UP    → Only LONG allowed. Full conviction uptrend.
    TREND_DOWN  → Only SHORT allowed. Full conviction downtrend.

TRANSITION is the critical new state. It's the danger window the old system
missed — when the market is leaving balance but OTF is not yet confirmed.

Output (emitted as MarketRegime_V2 event):
    {
        "type": "MarketRegime_V2",
        "regime": "BALANCE" | "TRANSITION" | "TREND_UP" | "TREND_DOWN",
        "direction": "UP" | "DOWN" | "NEUTRAL",
        "confidence": 0.0 - 1.0,
        "reversion_allowed": True | False,
        "layers": {
            "micro":  {"vote": "UP"|"DOWN"|"NEUTRAL", "score": float, "reason": str},
            "meso":   {"vote": "UP"|"DOWN"|"NEUTRAL", "score": float, "reason": str},
            "macro":  {"vote": "UP"|"DOWN"|"NEUTRAL", "score": float, "reason": str},
        },
        "va_expansion_rate": float,   # How fast VA is expanding (0 = tight, 1 = exploding)
        "poc_velocity": float,        # POC migration speed (signed, % per minute)
        "flow_momentum": float,       # Signed Z-score of recent delta flow
    }
"""

import logging
import time
from collections import deque
from typing import Any, Dict, Optional, Tuple

from sensors.base import SensorV3
from sensors.quant.volatility_regime import RollingZScore

logger = logging.getLogger("MarketRegimeSensor")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Layer 1 — Micro: tick-level flow momentum
MICRO_FLOW_WINDOW_SECONDS = 10.0  # Rolling window for delta accumulation
MICRO_SURGE_Z_THRESHOLD = 2.0  # Z-score to declare directional flow surge
MICRO_SNAPSHOT_HZ = 4.0  # Snapshots per second

# Layer 2 — Meso: VA expansion rate
MESO_VA_EXPANSION_FAST_WINDOW = 3  # Candles for fast VA width measurement
MESO_VA_EXPANSION_SLOW_WINDOW = 10  # Candles for slow VA width measurement
MESO_EXPANSION_THRESHOLD = 0.15  # 15% faster expansion = market leaving balance
MESO_IB_BREAK_WEIGHT = 0.4  # Extra weight if IB is broken with volume

# Layer 3 — Macro: POC migration velocity
MACRO_POC_HISTORY_WINDOW = 20  # Candles to measure POC velocity
MACRO_POC_VELOCITY_THRESHOLD = 0.0003  # 0.03% per candle = meaningful migration
MACRO_CONSECUTIVE_MIGRATION = 3  # N consecutive candles migrating = conviction

# Regime thresholds
TRANSITION_CONFIDENCE_MIN = 0.40  # Min confidence to declare TRANSITION
TREND_CONFIDENCE_MIN = 0.65  # Min confidence to declare TREND
BALANCE_MAX_CONFIDENCE = 0.35  # Max directional confidence to stay in BALANCE

# ---------------------------------------------------------------------------
# Phase 2300: Price Circuit Breaker — absolute price movement detector
# Bypasses Z-score normalization for extreme moves (crashes, rallies)
# ---------------------------------------------------------------------------
CIRCUIT_BREAKER_LOOKBACK = 10  # Candles to measure price displacement
CIRCUIT_BREAKER_TREND_PCT = 0.02  # 2% move in 10 candles = TREND (no Z-score needed)
CIRCUIT_BREAKER_CRASH_PCT = 0.04  # 4% move in 10 candles = TREND_DOWN (crash override)


class _PriceCircuitBreaker:
    """
    Phase 2300: Absolute Price Movement Detector.

    Problem with Z-score based regime detection:
    - Z-scores normalize against recent history
    - In a crash, the crash itself becomes the "normal" baseline
    - Result: sensor declares BALANCE during a 38% crash

    Solution: Measure raw price displacement over N candles.
    No normalization. No Z-scores. Pure price action.

    If price moved >2% in 10 candles → TREND (direction from sign)
    If price moved >4% in 10 candles → TREND with high confidence (crash/rally)

    This acts as a circuit breaker that overrides the microstructure layers
    when the market is in an extreme directional move.
    """

    def __init__(self):
        self.price_history: deque = deque(maxlen=CIRCUIT_BREAKER_LOOKBACK + 2)

    def on_candle(self, close: float, ts: float):
        if close > 0:
            self.price_history.append((ts, close))

    def evaluate(self) -> dict:
        """
        Returns circuit breaker verdict.

        Returns:
            {
                "triggered": bool,
                "direction": "UP" | "DOWN" | "NEUTRAL",
                "confidence": float,
                "displacement_pct": float,
                "reason": str
            }
        """
        if len(self.price_history) < CIRCUIT_BREAKER_LOOKBACK:
            return {
                "triggered": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "displacement_pct": 0.0,
                "reason": "insufficient_data",
            }

        oldest_price = self.price_history[0][1]
        current_price = self.price_history[-1][1]

        if oldest_price <= 0:
            return {
                "triggered": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "displacement_pct": 0.0,
                "reason": "invalid_price",
            }

        displacement = (current_price - oldest_price) / oldest_price  # signed
        abs_displacement = abs(displacement)
        direction = "UP" if displacement > 0 else "DOWN"

        # Crash/rally override: >4% in 10 candles
        if abs_displacement >= CIRCUIT_BREAKER_CRASH_PCT:
            confidence = min(1.0, abs_displacement / (CIRCUIT_BREAKER_CRASH_PCT * 2))
            return {
                "triggered": True,
                "direction": direction,
                "confidence": round(confidence, 3),
                "displacement_pct": round(displacement * 100, 3),
                "reason": "crash_rally_override",
            }

        # Normal trend: >2% in 10 candles
        if abs_displacement >= CIRCUIT_BREAKER_TREND_PCT:
            confidence = min(0.8, abs_displacement / (CIRCUIT_BREAKER_TREND_PCT * 3))
            return {
                "triggered": True,
                "direction": direction,
                "confidence": round(confidence, 3),
                "displacement_pct": round(displacement * 100, 3),
                "reason": "trend_override",
            }

        return {
            "triggered": False,
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "displacement_pct": round(displacement * 100, 3),
            "reason": "within_balance_range",
        }


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

        # Case 2: High delta velocity but price not moving → absorption (balance)
        if dv_z > MICRO_SURGE_Z_THRESHOLD and pv_z < 0.5:
            return {
                "vote": "NEUTRAL",
                "score": 0.0,
                "reason": "absorption_detected",
                "delta_vel": round(delta_vel, 2),
                "dv_z": round(dv_z, 2),
            }

        # Case 3: Weak or neutral flow
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
            # Direction from IB break if available, else ambiguous
            direction = ib_vote if ib_vote != "NEUTRAL" else "NEUTRAL"
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

        # Count consecutive migrations in the dominant direction
        consecutive_up = 0
        consecutive_down = 0
        for i in range(len(history) - 1, 0, -1):
            curr_poc = history[i][1]
            prev_poc = history[i - 1][1]
            if curr_poc > prev_poc:
                if consecutive_down > 0:
                    break
                consecutive_up += 1
            elif curr_poc < prev_poc:
                if consecutive_up > 0:
                    break
                consecutive_down += 1
            else:
                break  # POC didn't move — streak broken

        dominant_consecutive = max(consecutive_up, consecutive_down)
        direction = "UP" if consecutive_up > consecutive_down else "DOWN"

        # Score: combination of velocity magnitude and consecutive count
        vel_score = min(0.5, abs(velocity_per_candle) / (MACRO_POC_VELOCITY_THRESHOLD * 4))
        consec_score = min(0.5, dominant_consecutive / (MACRO_CONSECUTIVE_MIGRATION * 2))
        total_score = vel_score + consec_score

        if (
            abs(velocity_per_candle) > MACRO_POC_VELOCITY_THRESHOLD
            and dominant_consecutive >= MACRO_CONSECUTIVE_MIGRATION
        ):
            return {
                "vote": direction,
                "score": round(total_score, 3),
                "reason": "poc_migration_conviction",
                "velocity_per_candle": round(velocity_per_candle * 100, 5),
                "consecutive": dominant_consecutive,
            }

        if abs(velocity_per_candle) > MACRO_POC_VELOCITY_THRESHOLD:
            # Velocity present but not consecutive enough — early signal
            return {
                "vote": direction,
                "score": round(total_score * 0.5, 3),
                "reason": "poc_migration_early",
                "velocity_per_candle": round(velocity_per_candle * 100, 5),
                "consecutive": dominant_consecutive,
            }

        return {
            "vote": "NEUTRAL",
            "score": 0.0,
            "reason": "poc_stable",
            "velocity_per_candle": round(velocity_per_candle * 100, 5),
        }


class MarketRegimeSensor(SensorV3):
    """
    3-Layer Anticipatory Market Regime Sensor.

    Replaces OneTimeframing with a multi-layer conviction model that detects
    regime changes while they are occurring, not after they are confirmed.

    Integration:
        - Emits MarketRegime_V2 events consumed by SetupEngine.
        - SetupEngine maps regime to ContextRegistry (replaces set_regime/set_otf).
        - Guardian 1 (Regime Alignment) reads the new regime from ContextRegistry.

    Backward compatibility:
        - Also emits the legacy MarketRegime_OTF format so existing code
          that reads context_registry.get_regime() continues to work unchanged.
    """

    def __init__(self):
        super().__init__()
        self.symbol = "Unknown"

        # One set of layers per symbol (multi-symbol support)
        self._micro: Dict[str, _MicroLayer] = {}
        self._meso: Dict[str, _MesoLayer] = {}
        self._macro: Dict[str, _MacroLayer] = {}
        self._circuit: Dict[str, _PriceCircuitBreaker] = {}  # Phase 2300

        # Volume rolling average for IB break detection
        self._vol_history: Dict[str, deque] = {}

        # Last emitted regime per symbol (to avoid spamming identical events)
        self._last_regime: Dict[str, str] = {}
        self._last_emit_ts: Dict[str, float] = {}
        self._emit_interval = 5.0  # Minimum seconds between identical regime emissions

        # Candle volume history for avg calculation
        self._candle_vol_history: Dict[str, deque] = {}

    @property
    def name(self) -> str:
        return "MarketRegime"

    def _get_layers(self, symbol: str) -> Tuple[_MicroLayer, _MesoLayer, _MacroLayer]:
        """Lazy-initialize layers per symbol."""
        if symbol not in self._micro:
            self._micro[symbol] = _MicroLayer()
            self._meso[symbol] = _MesoLayer()
            self._macro[symbol] = _MacroLayer()
            self._circuit[symbol] = _PriceCircuitBreaker()  # Phase 2300
            self._candle_vol_history[symbol] = deque(maxlen=20)
        return self._micro[symbol], self._meso[symbol], self._macro[symbol]

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        """
        Process a raw tick for Layer 1 (micro flow).
        Called directly by SensorWorker on every tick.
        """
        symbol = tick_data.get("symbol", "Unknown")
        price = float(tick_data.get("price", 0))
        qty = float(tick_data.get("qty", 0))
        is_buyer_maker = tick_data.get("is_buyer_maker", False)
        ts = float(tick_data.get("timestamp", time.time()))

        if price <= 0 or qty <= 0:
            return None

        micro, _, _ = self._get_layers(symbol)
        micro.on_tick(price, qty, is_buyer_maker, ts)
        return None  # Tick-level updates don't emit — only candle-level does

    def calculate(self, context: Dict[str, Any]) -> Optional[dict]:
        """
        Main evaluation on each new 1m candle.
        Runs all 3 layers and synthesizes the regime verdict.
        """
        candle = context.get("1m")
        if not candle:
            return None

        symbol = candle.get("symbol", "Unknown")
        self.symbol = symbol

        poc = float(candle.get("poc") or 0.0)
        vah = float(candle.get("vah") or 0.0)
        val = float(candle.get("val") or 0.0)
        close = float(candle.get("close") or 0.0)
        volume = float(candle.get("volume") or 0.0)
        ts = float(candle.get("timestamp") or time.time())

        # IB levels from context (injected by SessionValueArea via ContextRegistry)
        ib_high = float(candle.get("ib_high") or 0.0) or None
        ib_low = float(candle.get("ib_low") or 0.0) or None

        micro, meso, macro = self._get_layers(symbol)

        # Update volume history for avg calculation
        self._candle_vol_history[symbol].append(volume)
        avg_volume = (
            sum(self._candle_vol_history[symbol]) / len(self._candle_vol_history[symbol])
            if self._candle_vol_history[symbol]
            else volume
        )

        # Feed layers
        meso.on_candle(poc, vah, val, ib_high, ib_low, close, volume, avg_volume, ts)
        macro.on_candle(poc, ts)

        # Phase 2300: Feed circuit breaker with raw price
        circuit = self._circuit[symbol]
        circuit.on_candle(close, ts)
        circuit_result = circuit.evaluate()

        # Evaluate all layers
        micro_result = micro.evaluate()
        meso_result = meso.evaluate(ts)
        macro_result = macro.evaluate()

        # Phase 2300: Circuit breaker takes priority over microstructure layers
        # If price moved >2% in 10 candles, override the Z-score based detection
        if circuit_result["triggered"]:
            cb_direction = circuit_result["direction"]
            cb_confidence = circuit_result["confidence"]
            cb_reason = circuit_result["reason"]

            if cb_reason == "crash_rally_override":
                # Extreme move: declare TREND immediately, bypass all layers
                regime = "TREND_UP" if cb_direction == "UP" else "TREND_DOWN"
                direction = cb_direction
                confidence = cb_confidence
                logger.warning(
                    f"🚨 [CIRCUIT_BREAKER] {symbol}: {cb_reason} → {regime} "
                    f"(displacement={circuit_result['displacement_pct']:.2f}%, conf={cb_confidence:.2f})"
                )
            else:
                # Normal trend: declare TREND but allow microstructure to confirm
                regime = "TREND_UP" if cb_direction == "UP" else "TREND_DOWN"
                direction = cb_direction
                confidence = cb_confidence
                logger.info(
                    f"⚡ [CIRCUIT_BREAKER] {symbol}: {cb_reason} → {regime} "
                    f"(displacement={circuit_result['displacement_pct']:.2f}%, conf={cb_confidence:.2f})"
                )

            reversion_allowed = False
        else:
            # Normal path: use microstructure layers
            regime, direction, confidence = self._synthesize(micro_result, meso_result, macro_result)
            reversion_allowed = regime == "BALANCE"

        # Build output
        output = {
            "type": "MarketRegime_V2",
            "regime": regime,
            "direction": direction,
            "confidence": round(confidence, 3),
            "reversion_allowed": reversion_allowed,
            "layers": {
                "micro": micro_result,
                "meso": meso_result,
                "macro": macro_result,
            },
            "circuit_breaker": circuit_result,  # Phase 2300
            "va_expansion_rate": meso_result.get("expansion_rate", 0.0),
            "poc_velocity": macro_result.get("velocity_per_candle", 0.0),
            "flow_momentum": micro_result.get("dv_z", 0.0),
        }

        # Throttle: only emit if regime changed or enough time passed
        last = self._last_regime.get(symbol, "")
        last_ts = self._last_emit_ts.get(symbol, 0.0)
        if regime == last and (ts - last_ts) < self._emit_interval:
            return None

        self._last_regime[symbol] = regime
        self._last_emit_ts[symbol] = ts

        # Log regime transitions prominently
        if regime != last and last != "":
            emoji = {"BALANCE": "⚖️", "TRANSITION": "⚠️", "TREND_UP": "🚀", "TREND_DOWN": "📉"}.get(regime, "🔄")
            logger.warning(
                f"{emoji} [REGIME] {symbol}: {last} → {regime} "
                f"(confidence={confidence:.2f}, dir={direction}) | "
                f"micro={micro_result['vote']}({micro_result['score']:.2f}) "
                f"meso={meso_result['vote']}({meso_result['score']:.2f}) "
                f"macro={macro_result['vote']}({macro_result['score']:.2f})"
            )

        return {
            "side": "NEUTRAL",
            "score": confidence,
            "metadata": output,
        }

    def _synthesize(
        self,
        micro: dict,
        meso: dict,
        macro: dict,
    ) -> Tuple[str, str, float]:
        """
        Synthesize the 3 layer votes into a single regime verdict.

        Voting weights:
            Micro:  0.25  (fast but noisy)
            Meso:   0.35  (structural, medium speed)
            Macro:  0.40  (slow but most reliable)

        Logic:
            1. Calculate weighted directional score for UP and DOWN.
            2. Net score = UP_score - DOWN_score (signed).
            3. Map to regime based on thresholds.

        Special cases:
            - If micro and meso agree but macro doesn't → TRANSITION (early warning)
            - If all 3 agree → TREND (full conviction)
            - If none agree → BALANCE
        """
        WEIGHTS = {"micro": 0.25, "meso": 0.35, "macro": 0.40}

        def directional_score(layer_result: dict, weight: float) -> Tuple[float, float]:
            """Returns (up_contribution, down_contribution)."""
            vote = layer_result.get("vote", "NEUTRAL")
            score = layer_result.get("score", 0.0)
            if vote == "UP":
                return score * weight, 0.0
            if vote == "DOWN":
                return 0.0, score * weight
            return 0.0, 0.0

        up_total = 0.0
        down_total = 0.0

        for layer_name, layer_result in [("micro", micro), ("meso", meso), ("macro", macro)]:
            up_c, down_c = directional_score(layer_result, WEIGHTS[layer_name])
            up_total += up_c
            down_total += down_c

        net_score = up_total - down_total  # Positive = bullish, Negative = bearish
        abs_score = abs(net_score)
        direction = "UP" if net_score > 0 else ("DOWN" if net_score < 0 else "NEUTRAL")

        # Count how many layers agree on the dominant direction
        dominant_votes = sum(1 for r in [micro, meso, macro] if r.get("vote") == direction and r.get("score", 0) > 0)

        # --- Regime Classification ---

        # BALANCE: Low directional conviction
        if abs_score < BALANCE_MAX_CONFIDENCE:
            return "BALANCE", "NEUTRAL", abs_score

        # TRANSITION: Medium conviction OR early warning (2 layers agree, macro lags)
        # This is the critical new state — market is leaving balance
        if abs_score >= TRANSITION_CONFIDENCE_MIN:
            # Check if it's a full TREND or just TRANSITION
            if abs_score >= TREND_CONFIDENCE_MIN and dominant_votes >= 2:
                regime = "TREND_UP" if direction == "UP" else "TREND_DOWN"
                return regime, direction, abs_score

            # Macro alone can declare TREND even without micro/meso
            # (slow but reliable — if macro says trend, trust it)
            if macro.get("vote") == direction and macro.get("score", 0) >= 0.4:
                regime = "TREND_UP" if direction == "UP" else "TREND_DOWN"
                return regime, direction, abs_score

            # Early warning: micro + meso agree but macro hasn't confirmed yet
            # This is the TRANSITION state — block reversions NOW, before OTF fires
            if (
                micro.get("vote") == direction
                and micro.get("score", 0) > 0
                and meso.get("vote") == direction
                and meso.get("score", 0) > 0
            ):
                return "TRANSITION", direction, abs_score

            # Single layer with medium conviction
            return "TRANSITION", direction, abs_score

        # Fallback: BALANCE
        return "BALANCE", "NEUTRAL", abs_score
