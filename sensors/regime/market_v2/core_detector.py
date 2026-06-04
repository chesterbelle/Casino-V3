"""
Regime Sensor V2 — MarketRegimeSensorV2

2-Layer Architecture:
  Layer 1: Price Action (lead detector) — trend direction via swing points
  Layer 2: Volume Profile (confirmation) — POC migration + VA position
  Memory: Markov chain — Bayesian prior for regime persistence

Replaces the 3-layer architecture (Micro=dead, Meso=almost dead, Macro=lagging)
with 2 simple, effective layers that actually contribute to regime detection.

Integration:
  - Same interface as MarketRegimeSensor (drop-in replacement)
  - Emits MarketRegime_V2 events consumed by SetupEngine
  - Compatible with existing Markov matrix (config/markov_transition.json)
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

from sensors.base import SensorV3
from sensors.regime.market_v2.layers import _PriceActionLayer, _VolumeProfileLayer
from sensors.regime.market_v2.synthesis import synthesize
from sensors.regime.markov_detector import MarkovRegimeDetector

logger = logging.getLogger("MarketRegimeSensorV2")


class MarketRegimeSensorV2(SensorV3):
    """
    2-Layer Anticipatory Market Regime Sensor.

    Architecture:
      Layer 1: Price Action (lead) — detects trend via swing structure
      Layer 2: Volume Profile (confirm) — confirms via POC migration + VA
      Memory: Markov — Bayesian prior for persistence

    Backward compatibility:
      - Same output format as MarketRegimeSensor V1
      - Same integration points (SetupEngine, ContextRegistry)
    """

    def __init__(self):
        super().__init__()
        self.symbol = "Unknown"

        # One set of layers per symbol (multi-symbol support)
        self._price_action: Dict[str, _PriceActionLayer] = {}
        self._volume_profile: Dict[str, _VolumeProfileLayer] = {}

        # Markov memory per symbol
        self._markov: Dict[str, MarkovRegimeDetector] = {}
        self._markov_config_path = "config/markov_transition.json"

        # Previous close for return calculation
        self._prev_close: Dict[str, float] = {}

        # Last emitted regime per symbol (to avoid spamming identical events)
        self._last_regime: Dict[str, str] = {}
        self._last_emit_ts: Dict[str, float] = {}
        self._emit_interval = 5.0

        # Persistence state per symbol
        self._persistent_regime: Dict[str, str] = {}
        self._persistent_direction: Dict[str, str] = {}
        self._persistent_reference: Dict[str, float] = {}
        self._persistent_count: Dict[str, int] = {}
        self._persistence_reset_threshold = 0.004  # 0.4% reversal to reset
        self._persistence_decay_window = 5  # Candles before release

    @property
    def name(self) -> str:
        return "MarketRegime"

    def _get_layers(self, symbol: str) -> Tuple[_PriceActionLayer, _VolumeProfileLayer]:
        """Lazy-initialize layers per symbol."""
        if symbol not in self._price_action:
            self._price_action[symbol] = _PriceActionLayer()
            self._volume_profile[symbol] = _VolumeProfileLayer()

            # Initialize Markov detector
            markov = MarkovRegimeDetector()
            try:
                markov.load(self._markov_config_path)
                logger.info(f"Loaded Markov matrix for {symbol}")
            except FileNotFoundError:
                logger.warning(f"No Markov matrix found — {symbol} running without memory")
            except Exception as e:
                logger.warning(f"Failed to load Markov matrix: {e}")
            self._markov[symbol] = markov

        return self._price_action[symbol], self._volume_profile[symbol]

    def on_tick(self, tick_data: dict) -> Optional[dict]:
        """Tick-level updates not used in V2 (price action is candle-based)."""
        return None

    def calculate(self, context: Dict[str, Any]) -> Optional[dict]:
        """
        Main evaluation on each new 1m candle.
        Runs both layers and synthesizes the regime verdict.
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
        high = float(candle.get("high") or 0.0)
        low = float(candle.get("low") or 0.0)
        volume = float(candle.get("volume") or 0.0)
        ts = float(candle.get("timestamp") or time.time())

        pa, vp = self._get_layers(symbol)

        # Feed layers
        pa.on_candle(high, low, close, ts)
        vp.on_candle(poc, vah, val, close, volume, ts)

        # Evaluate layers
        pa_result = pa.evaluate()
        vp_result = vp.evaluate()

        # Update Markov memory
        markov = self._markov.get(symbol)
        if markov and markov._trained:
            if symbol in self._prev_close and self._prev_close[symbol] > 0:
                ret = (close - self._prev_close[symbol]) / self._prev_close[symbol]
                markov.update(ret)
            self._prev_close[symbol] = close

        # Synthesize
        synth = synthesize(pa_result, vp_result, markov)
        regime = synth["regime"]
        direction = synth["direction"]
        confidence = synth["confidence"]
        value_acceptance = synth["value_acceptance"]
        absorption_detected = synth["absorption_detected"]

        # --- Persistence logic ---
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

            if should_reset:
                # Price reversed → allow regime change
                self._persistent_regime[symbol] = regime
                self._persistent_direction[symbol] = direction
                self._persistent_reference[symbol] = close
                self._persistent_count[symbol] = 0
            elif persist_count < self._persistence_decay_window:
                # Within decay window → maintain previous regime
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
        markov_data = {}
        if markov and markov._trained:
            priors = markov.get_prior()
            markov_data = {
                "prior_BALANCE": round(priors["BALANCE"], 3),
                "prior_UP": round(priors["UP"], 3),
                "prior_DOWN": round(priors["DOWN"], 3),
            }

        output = {
            "type": "MarketRegime_V2",
            "regime": regime,
            "direction": direction,
            "confidence": round(confidence, 3),
            "reversion_allowed": reversion_allowed,
            "value_acceptance": value_acceptance,
            "absorption_detected": absorption_detected,
            "layers": {
                "price_action": pa_result,
                "volume_profile": vp_result,
            },
            "markov": markov_data,
            "va_expansion_rate": vp_result.get("va_expansion_rate", 0.0),
            "poc_velocity": vp_result.get("poc_velocity", 0.0),
            "flow_momentum": pa_result.get("momentum", 0.0),
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
            markov_str = ""
            if markov and markov._trained:
                priors = markov.get_prior()
                markov_str = f" | Markov: B={priors['BALANCE']:.2f} U={priors['UP']:.2f} D={priors['DOWN']:.2f}"
            logger.warning(
                f"{emoji} [REGIME_V2] {symbol}: {last} → {regime} "
                f"(confidence={confidence:.2f}, dir={direction}) | "
                f"PA={pa_result['vote']}({pa_result['score']:.2f}) "
                f"VP={vp_result['vote']}({vp_result['score']:.2f})"
                f"{markov_str}"
            )

        return {
            "side": "NEUTRAL",
            "score": confidence,
            "metadata": output,
        }
