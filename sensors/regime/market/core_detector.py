import logging
import time
from collections import deque
from typing import Any, Dict, Optional, Tuple

from sensors.base import SensorV3
from sensors.regime.market.trend_calc import _MacroLayer, _MesoLayer, _MicroLayer
from sensors.regime.market.volatility_calc import _PriceCircuitBreaker

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
        self._circuit: Dict[str, _PriceCircuitBreaker] = {}

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
            self._circuit[symbol] = _PriceCircuitBreaker()
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

        # Feed circuit breaker with raw price
        circuit = self._circuit[symbol]
        circuit.on_candle(close, ts)
        circuit_result = circuit.evaluate()

        # Evaluate all layers
        micro_result = micro.evaluate()
        meso_result = meso.evaluate(ts)
        macro_result = macro.evaluate()

        # Circuit breaker takes priority over microstructure layers
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
            value_acceptance = "ACCEPTING"  # Crash/rally = market accepting new prices
            absorption_detected = False
        else:
            # Normal path: use microstructure layers
            synth = self._synthesize(micro_result, meso_result, macro_result)
            regime = synth["regime"]
            direction = synth["direction"]
            confidence = synth["confidence"]
            value_acceptance = synth["value_acceptance"]
            absorption_detected = synth["absorption_detected"]
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
            "circuit_breaker": circuit_result,
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
        V3 Synthesis: Value Position × Value Acceptance model.

        Instead of BALANCE/TRANSITION/TREND, we determine:
        - Is the market ACCEPTING new prices (trend continuation)?
        - Is the market REJECTING new prices (absorption → reversion)?
        - Is the market NEUTRAL (no conviction)?

        The guardian combines value_acceptance with Z-score
        (IN_VALUE vs OUT_OF_VALUE) to determine SetupMode.

        TRANSITION state is eliminated — either the market has
        conviction (TREND) or it doesn't (BALANCE).
        """
        WEIGHTS = {"micro": 0.25, "meso": 0.35, "macro": 0.40}

        def directional_score(layer_result: dict, weight: float) -> Tuple[float, float]:
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

        net_score = up_total - down_total
        abs_score = abs(net_score)
        direction = "UP" if net_score > 0 else ("DOWN" if net_score < 0 else "NEUTRAL")

        # Count how many layers agree on the dominant direction
        dominant_votes = sum(1 for r in [micro, meso, macro] if r.get("vote") == direction and r.get("score", 0) > 0)

        # Detect absorption from micro layer (high delta velocity, no price movement)
        absorption_detected = micro.get("reason") == "absorption_detected"

        # Determine value acceptance
        if absorption_detected:
            value_acceptance = "REJECTING"
        elif dominant_votes >= 2 and abs_score > BALANCE_MAX_CONFIDENCE:
            value_acceptance = "ACCEPTING"
        else:
            value_acceptance = "NEUTRAL"

        # --- Regime Classification (no TRANSITION) ---

        # Macro high-conviction override: if POC migration is very strong,
        # declare TREND directly, bypassing weighted synthesis
        # This solves the "BEAR Gap": macro alone can detect slow drift even
        # when micro/meso are neutral (choppy bear with no CVD surge or VA expansion)
        macro_score = macro.get("score", 0)
        macro_dir = macro.get("vote", "NEUTRAL")
        if macro_score >= 0.6 and macro_dir in ("UP", "DOWN"):
            regime = "TREND_UP" if macro_dir == "UP" else "TREND_DOWN"
            return {
                "regime": regime,
                "direction": macro_dir,
                "confidence": max(abs_score, macro_score * 0.85),
                "value_acceptance": value_acceptance,
                "absorption_detected": absorption_detected,
            }

        # BALANCE: Low directional conviction
        if abs_score < BALANCE_MAX_CONFIDENCE:
            return {
                "regime": "BALANCE",
                "direction": "NEUTRAL",
                "confidence": abs_score,
                "value_acceptance": value_acceptance,
                "absorption_detected": absorption_detected,
            }

        # TREND: Full conviction (2+ layers agree + high score)
        if abs_score >= TREND_CONFIDENCE_MIN and dominant_votes >= 2:
            regime = "TREND_UP" if direction == "UP" else "TREND_DOWN"
            return {
                "regime": regime,
                "direction": direction,
                "confidence": abs_score,
                "value_acceptance": value_acceptance,
                "absorption_detected": absorption_detected,
            }

        # Macro alone can declare TREND (slow but reliable)
        # Threshold reduced from 0.4→0.25: in slow BEAR (-5% over 24h),
        # POC migration velocity is only ~0.0038%/candle, yielding macro.score ≈ 0.20
        # Old 0.4 threshold only fired ~15% of BEAR time; 0.25 fires ~35-45%
        if macro.get("vote") == direction and macro.get("score", 0) >= 0.25:
            regime = "TREND_UP" if direction == "UP" else "TREND_DOWN"
            # Escalate confidence: if macro is the only layer with conviction,
            # its score should reflect more directly in the output confidence
            escalated_confidence = max(abs_score, macro.get("score", 0) * 0.85)
            return {
                "regime": regime,
                "direction": direction,
                "confidence": escalated_confidence,
                "value_acceptance": value_acceptance,
                "absorption_detected": absorption_detected,
            }

        # Micro + meso agree → early TREND (was TRANSITION, now TREND)
        if (
            micro.get("vote") == direction
            and micro.get("score", 0) > 0
            and meso.get("vote") == direction
            and meso.get("score", 0) > 0
        ):
            regime = "TREND_UP" if direction == "UP" else "TREND_DOWN"
            return {
                "regime": regime,
                "direction": direction,
                "confidence": abs_score,
                "value_acceptance": value_acceptance,
                "absorption_detected": absorption_detected,
            }

        # Single layer with weak conviction → BALANCE (was TRANSITION)
        return {
            "regime": "BALANCE",
            "direction": direction,
            "confidence": abs_score,
            "value_acceptance": value_acceptance,
            "absorption_detected": absorption_detected,
        }
