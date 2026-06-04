import logging
import time
from collections import deque
from typing import Any, Dict, Optional, Tuple

from sensors.base import SensorV3
from sensors.regime.market.trend_calc import _MacroLayer, _MesoLayer, _MicroLayer

logger = logging.getLogger("MarketRegimeSensor")

# Regime thresholds - Iteration 1: Reduce confidence thresholds for better TREND detection
TRANSITION_CONFIDENCE_MIN = 0.30  # Min confidence to declare TRANSITION (from 0.40)
TREND_CONFIDENCE_MIN = 0.55  # Min confidence to declare TREND (reduced from 0.65)
BALANCE_MAX_CONFIDENCE = 0.15  # Max directional confidence to stay in BALANCE (reduced from 0.20)


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

        # Volume rolling average for IB break detection
        self._vol_history: Dict[str, deque] = {}

        # Last emitted regime per symbol (to avoid spamming identical events)
        self._last_regime: Dict[str, str] = {}
        self._last_emit_ts: Dict[str, float] = {}
        self._emit_interval = 5.0  # Minimum seconds between identical regime emissions

        # Persistence state per symbol (matches GT regime persistence logic)
        self._persistent_regime: Dict[str, str] = {}
        self._persistent_direction: Dict[str, str] = {}
        self._persistent_reference: Dict[str, float] = {}
        self._persistent_count: Dict[str, int] = {}
        self._persistence_reset_threshold = 0.005  # 0.5% reversal to reset

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

        # Evaluate all layers
        micro_result = micro.evaluate()
        meso_result = meso.evaluate(ts)
        macro_result = macro.evaluate()

        # Normal path: use microstructure layers
        synth = self._synthesize(micro_result, meso_result, macro_result)
        regime = synth["regime"]
        direction = synth["direction"]
        confidence = synth["confidence"]
        value_acceptance = synth["value_acceptance"]
        absorption_detected = synth["absorption_detected"]

        # --- Persistence logic ---
        # If synthesis says BALANCE but we were in TREND and price hasn't
        # reversed enough, maintain the TREND. This prevents the sensor from
        # flickering between TREND and BALANCE every candle.
        # Persistence decays if macro stops confirming: after 5 candles without
        # macro confirmation, persistence releases.
        prev_regime = self._persistent_regime.get(symbol, "BALANCE")
        prev_direction = self._persistent_direction.get(symbol, "NEUTRAL")
        prev_ref = self._persistent_reference.get(symbol, 0.0)
        persist_count = self._persistent_count.get(symbol, 0)

        if prev_regime.startswith("TREND") and prev_ref > 0:
            # Check if price has reversed enough to reset
            if prev_direction == "UP":
                pullback = (prev_ref - close) / prev_ref
                should_reset = pullback > self._persistence_reset_threshold
            elif prev_direction == "DOWN":
                recovery = (close - prev_ref) / prev_ref
                should_reset = recovery > self._persistence_reset_threshold
            else:
                should_reset = True

            # Check if macro still confirms the persistent direction
            macro_confirms = macro_result.get("vote") == prev_direction and macro_result.get("score", 0) >= 0.10

            if should_reset:
                # Price reversed → allow regime change
                self._persistent_regime[symbol] = regime
                self._persistent_direction[symbol] = direction
                self._persistent_reference[symbol] = close
                self._persistent_count[symbol] = 0
            elif macro_confirms:
                # Macro confirms → maintain and update reference
                self._persistent_regime[symbol] = regime if regime.startswith("TREND") else prev_regime
                self._persistent_direction[symbol] = direction if regime.startswith("TREND") else prev_direction
                self._persistent_reference[symbol] = close
                self._persistent_count[symbol] = 0
            elif persist_count < 5:
                # No macro confirmation but within decay window → maintain
                self._persistent_count[symbol] = persist_count + 1
                regime = prev_regime
                direction = prev_direction
                confidence = confidence * 0.85
            else:
                # Decay expired → release persistence
                self._persistent_regime[symbol] = regime
                self._persistent_direction[symbol] = direction
                self._persistent_reference[symbol] = close
                self._persistent_count[symbol] = 0
        else:
            # No previous TREND → accept synthesis output
            self._persistent_regime[symbol] = regime
            self._persistent_direction[symbol] = direction
            self._persistent_reference[symbol] = close
            self._persistent_count[symbol] = 0

        reversion_allowed = value_acceptance != "ACCEPTING"

        # Build output
        output = {
            "type": "MarketRegime_V2",
            "regime": regime,
            "direction": direction,
            "confidence": round(confidence, 3),
            "reversion_allowed": reversion_allowed,
            "value_acceptance": value_acceptance,
            "absorption_detected": absorption_detected,
            "layers": {
                "micro": micro_result,
                "meso": meso_result,
                "macro": macro_result,
            },
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
            emoji = {"BALANCE": "⚖️", "TREND_UP": "🚀", "TREND_DOWN": "📉"}.get(regime, "🔄")
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
    ) -> dict:
        """
        Hierarchical Synthesis v2: Macro leads → Meso confirms → Micro filters.

        Replaces the old equal-weight voting model which suffered from:
        - Layers operating on inconmensurable timeframes (10s vs 3-10c vs 20c)
        - Micro being noise, not signal
        - Meso having ambiguous direction in mid-VA closes
        - Consensus almost never reached → chronic BALANCE bias

        New model:
        Level 1 — MACRO (Lead Detector):
          POC migration is the most reliable indicator of sustained trend.
          If macro.score >= 0.25 and vote != NEUTRAL → declares TREND.

        Level 2 — MESO (Confirmator / Veto):
          If meso votes OPPOSITE with score >= 0.3 → vetoes, degrades to BALANCE.
          If meso votes SAME or NEUTRAL → confirms, confidence escalates.

        Level 3 — MICRO (Noise Filter):
          Does NOT vote for regime. Only detects absorption.
          If absorption_detected → marks value_acceptance = "REJECTING".
        """
        # Level 3: Micro = absorption detection only
        absorption_detected = micro.get("reason") == "absorption_detected"

        # Level 1: Macro leads
        macro_score = macro.get("score", 0)
        macro_vote = macro.get("vote", "NEUTRAL")

        if macro_score < 0.15 or macro_vote == "NEUTRAL":
            # Macro has no conviction → BALANCE
            return {
                "regime": "BALANCE",
                "direction": "NEUTRAL",
                "confidence": macro_score,
                "value_acceptance": "REJECTING" if absorption_detected else "NEUTRAL",
                "absorption_detected": absorption_detected,
            }

        # Macro has conviction — declare TREND direction
        direction = macro_vote
        regime = f"TREND_{direction}"

        # Level 2: Meso confirms or vetoes
        meso_vote = meso.get("vote", "NEUTRAL")
        meso_score = meso.get("score", 0)

        # Veto: meso strongly disagrees → degrade to BALANCE
        if meso_vote != "NEUTRAL" and meso_vote != direction and meso_score >= 0.2:
            return {
                "regime": "BALANCE",
                "direction": "NEUTRAL",
                "confidence": macro_score * 0.5,
                "value_acceptance": "REJECTING" if absorption_detected else "NEUTRAL",
                "absorption_detected": absorption_detected,
            }

        # Confirmation: meso agrees or is neutral → confidence escalates
        if meso_vote == direction and meso_score > 0:
            confidence = max(macro_score, (macro_score + meso_score) / 2)
        else:
            confidence = macro_score * 0.85

        # Value acceptance
        if absorption_detected:
            value_acceptance = "REJECTING"
        elif meso_vote == direction and meso_score > 0:
            value_acceptance = "ACCEPTING"
        else:
            value_acceptance = "NEUTRAL"

        return {
            "regime": regime,
            "direction": direction,
            "confidence": round(confidence, 3),
            "value_acceptance": value_acceptance,
            "absorption_detected": absorption_detected,
        }
