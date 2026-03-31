"""
Fixed Player Strategy
=====================

A simple player that bets a fixed percentage of equity on every signal.
Supports optional Kelly Criterion sizing based on sensor performance.
"""

import asyncio
import logging
import time
from typing import Optional, Tuple

from core.events import AggregatedSignalEvent, Event, EventType
from decision.sensor_tracker import SensorTracker

logger = logging.getLogger(__name__)


class DecisionEvent(Event):
    """Decision event with bet sizing and absolute TP/SL prices."""

    def __init__(
        self,
        symbol: str,
        side: str,
        bet_size: float,
        tp_pct: float = None,
        sl_pct: float = None,
        tp_price: float = None,
        sl_price: float = None,
        selected_sensor: str = None,
        t0_timestamp: float = None,
        t1_decision_ts: float = None,
        trace_id: str = None,
        setup_type: str = None,
        atr_1m: float = 0.0,
        timestamp: Optional[float] = None,
    ):
        super().__init__(type=EventType.DECISION, timestamp=timestamp or time.time())
        self.t0_timestamp = t0_timestamp
        self.t1_decision_ts = t1_decision_ts
        self.trace_id = trace_id
        self.setup_type = setup_type
        self.symbol = symbol
        self.side = side
        self.bet_size = bet_size
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.tp_price = tp_price  # Absolute TP price (primary)
        self.sl_price = sl_price  # Absolute SL price (primary)
        self.selected_sensor = selected_sensor
        self.atr_1m = atr_1m
        # Compatibility fields for logging/Paroli
        self.paroli_step = 0
        self.unit_size = 0.0


class AdaptivePlayer:
    """
    Adaptive player that sizes bets based on sensor performance.

    Supports two modes:
    1. Fixed: Always bet fixed_pct (fallback)
    2. Kelly: Dynamically size based on sensor's historical performance
    """

    def __init__(
        self,
        engine,
        croupier,
        fixed_pct: float = 0.01,
        max_positions: int = 1,
        use_kelly: bool = True,
        kelly_max: float = 0.10,
        context_registry=None,
        fast_track: bool = False,
    ):
        """
        Args:
            engine: Event engine
            croupier: Croupier for position management
            fixed_pct: Fixed bet size as fraction of equity (fallback)
            max_positions: Maximum concurrent positions
            use_kelly: If True, use Kelly sizing for sensors with enough data
            kelly_max: Maximum Kelly fraction (safety cap)
        """
        self.engine = engine
        self.croupier = croupier
        self.fixed_pct = fixed_pct
        self.max_positions = max_positions
        self.use_kelly = use_kelly
        self.kelly_max = kelly_max
        self.context_registry = context_registry
        self.fast_track = fast_track

        # SensorTracker for Kelly calculations
        self.tracker = SensorTracker()

        # Subscribe to Aggregated Signals
        self.engine.subscribe(EventType.AGGREGATED_SIGNAL, self.on_aggregated_signal)

        mode = "Kelly" if use_kelly else "Fixed"
        logger.info(
            f"✅ FixedPlayer initialized | Mode: {mode} | "
            f"Bet Size: {fixed_pct:.1%} | Kelly Max: {kelly_max:.1%} | "
            f"Max Positions: {max_positions}"
        )

    def _get_best_htf_levels(self, metadata: dict) -> dict:
        """
        Phase 700: Get the most relevant HTF levels from metadata.
        Priority: 1h > 15m > 4h (1h is optimal balance for scalping).
        Returns dict with poc, vah, val and source_tf.
        """
        for tf in ("1h", "15m", "4h"):
            poc = metadata.get(f"{tf}_poc")
            vah = metadata.get(f"{tf}_vah")
            val = metadata.get(f"{tf}_val")
            if poc and poc > 0 and vah and vah > 0 and val and val > 0:
                return {"poc": poc, "vah": vah, "val": val, "source_tf": tf}
        return {}

    def _calculate_structural_tp_sl(
        self, side: str, entry_price: float, htf_levels: dict, setup_type: str, regime: str = "NORMAL"
    ) -> Tuple[Optional[float], Optional[float]]:
        poc = htf_levels.get("poc")
        vah = htf_levels.get("vah")
        val = htf_levels.get("val")

        if not all([poc, vah, val]) or entry_price <= 0:
            return None, None

        tp_price = None
        sl_price = None

        # Phase 650: REGIME-AWARE EXIT STRATEGIES
        if regime == "TREND_WINDOW":
            # In TREND, we give the trade more room to breathe and target extensions
            # SL is tighter to entry (protecting capital) but TP is wider
            if side == "LONG":
                tp_price = vah * 1.005  # Target extension above VAH
                sl_price = entry_price * 0.998  # Tighter 0.2% SL
            else:
                tp_price = val * 0.995  # Target extension below VAL
                sl_price = entry_price * 1.002
        elif regime == "RANGE_WINDOW":
            # In RANGE, we scalp specifically between POC and extremes
            # TP is hard-gated at the opposite boundary
            if side == "LONG":
                tp_price = vah if entry_price < poc else vah * 1.002
                sl_price = min(entry_price * 0.998, val * 0.999)
            else:
                tp_price = val if entry_price > poc else val * 0.998
                sl_price = max(entry_price * 1.002, vah * 1.001)
        else:
            # NORMAL/DEVELOPING: Legacy structural logic
            if setup_type == "reversion":
                if side == "LONG":
                    tp_price = poc
                    sl_price = min(entry_price * 0.998, val * 0.999)
                else:
                    tp_price = poc
                    sl_price = max(entry_price * 1.002, vah * 1.001)
            else:
                if side == "LONG":
                    tp_price = vah
                    sl_price = min(entry_price * 0.998, poc * 0.999)
                else:
                    tp_price = val
                    sl_price = max(entry_price * 1.002, poc * 1.001)

        # Final Sanity Check: Ensure structural targets make sense relative to entry
        if tp_price and sl_price:
            if side == "LONG":
                if tp_price <= entry_price or sl_price >= entry_price:
                    return None, None
            elif side == "SHORT":
                if tp_price >= entry_price or sl_price <= entry_price:
                    return None, None
            return tp_price, sl_price

        return None, None

    async def on_aggregated_signal(self, event: AggregatedSignalEvent):
        """Process aggregated signal and place bet."""
        if event.side == "SKIP":
            return

        # Check position limit
        # Check position limit (PER SYMBOL)
        # Fix: Normalize symbol strings to handle LTCUSDT vs LTC/USDT mismatch
        # Phase 234: Use get_active_positions to ignore CLOSING/OFF_BOARDING
        open_positions = self.croupier.get_active_positions()

        target_symbol_norm = event.symbol.replace("/", "")
        symbol_positions = [p for p in open_positions if p.symbol.replace("/", "") == target_symbol_norm]

        if len(symbol_positions) >= self.max_positions:
            logger.debug(
                f"⏭️ Skipping signal for {event.symbol} - "
                f"at symbol position limit ({len(symbol_positions)}/{self.max_positions})"
            )
            return

        # Check for matching pending intent (Race Condition Fix)
        if hasattr(self.croupier, "is_pending") and self.croupier.is_pending(event.symbol):
            logger.warning(f"⏭️ Skipping signal for {event.symbol} - Pending Order In-Flight (Debounce)")
            return

        # Get current equity
        equity = self.croupier.get_equity()

        # Phase 650: Synchronous Regime Lookup (Zero-Lag Mirror)
        regime = "NORMAL"
        if self.context_registry:
            regime = self.context_registry.get_regime(event.symbol)

        # Calculate bet size
        if self.use_kelly:
            # Use Kelly sizing based on sensor performance
            kelly_bet = self.tracker.get_kelly_fraction(event.selected_sensor, max_fraction=self.kelly_max)
            bet_size = kelly_bet
            sizing_method = "Kelly"
        else:
            # Use fixed percentage
            bet_size = self.fixed_pct
            sizing_method = "Fixed"

        # Apply Sizing Multipliers based on Regime
        if regime == "TREND_WINDOW":
            bet_size *= 1.25  # Aggressive in trend
        elif regime == "RANGE_WINDOW":
            bet_size *= 0.75  # Defensive in range (mean reversion is noisier)

        # Phase 1600: Delta-Velocity Sizing Lead
        dv_multiplier = event.metadata.get("dv_multiplier", 1.0)
        bet_size *= dv_multiplier

        # Phase 1300: Placeholder bet_size for later RR-scaling
        base_bet_size = bet_size

        # Phase 800: Unified TP/SL pipeline — absolute prices are primary
        tp_price = None
        sl_price = None

        setup_type = getattr(event, "setup_type", event.metadata.get("setup_type", "unknown"))
        tp_sl_source = "config_fallback"

        # Phase 700: Structural TP/SL from SetupEngine levels
        current_price = event.metadata.get("price")
        # Setup engine provides poc/vah/val in metadata directly, so we can use those.
        poc = event.metadata.get("poc")
        vah = event.metadata.get("vah")
        val = event.metadata.get("val")

        # Phase 600: James Dalton Contextual Exits (fallback if no structural levels already set)
        if tp_price is None and "poc" in event.metadata and "vah" in event.metadata and "val" in event.metadata:
            poc = event.metadata["poc"]
            vah = event.metadata["vah"]
            val = event.metadata["val"]
            if not current_price:
                current_price = event.metadata.get("price")

            if current_price and current_price > 0:
                tp_sl_source = "dalton_context"
                if event.side == "LONG":
                    # Phase 1205: Hardened Structural Targets (Long)
                    if current_price <= poc:
                        tp_price = max(poc, current_price * 1.0035)  # Target POC or 0.35%
                    else:
                        tp_price = max(vah, current_price * 1.0035)  # Target VAH or 0.35%
                    sl_price = min(val * 0.999, current_price * 0.997)  # Target VAL or 0.3%

                elif event.side == "SHORT":
                    # Phase 1205: Hardened Structural Targets (Short)
                    if current_price >= poc:
                        tp_price = min(poc, current_price * 0.9965)  # Target POC or 0.35%
                    else:
                        tp_price = min(val, current_price * 0.9965)  # Target VAL or 0.35%
                    sl_price = max(vah * 1.001, current_price * 1.003)  # Target VAH or 0.3%

        # Phase 650.2: Unfinished Business Exact Targeting (absolute price override)
        unfinished_targets = event.metadata.get("unfinished_business_targets", [])
        if unfinished_targets and current_price and current_price > 0:
            for target in unfinished_targets:
                if event.side == "LONG" and target.get("side") == "LONG_TARGET":
                    dist_pct = (target["price"] - current_price) / current_price
                    if dist_pct > 0.0005:  # at least 0.05% away
                        tp_price = target["price"]
                        logger.debug(f"🎯 Unfinished Business TARGET: Override TP to {tp_price:.4f}")
                        tp_sl_source = "unfinished_business"
                elif event.side == "SHORT" and target.get("side") == "SHORT_TARGET":
                    dist_pct = (current_price - target["price"]) / current_price
                    if dist_pct > 0.0005:
                        tp_sl_source = "unfinished_business"

        # Phase 800: Direct Metadata Fallback (if sensors provide absolute prices)
        if tp_price is None:
            tp_price = event.metadata.get("tp_price")
            if tp_price:
                tp_sl_source = "metadata_direct"
        if sl_price is None:
            sl_price = event.metadata.get("sl_price")
            if sl_price:
                tp_sl_source = "metadata_direct"

        # Phase 1300: ATR-Based TP/SL Fallback (when structural levels are missing)
        if tp_price is None or sl_price is None:
            if current_price and current_price > 0:
                # Generate reasonable TP/SL based on setup type
                if setup_type == "reversion":
                    tp_pct_fallback = 0.50  # 0.50% TP for mean reversion
                    sl_pct_fallback = 0.30  # 0.30% SL for mean reversion
                elif setup_type == "continuation":
                    tp_pct_fallback = 0.60  # 0.60% TP for breakout continuation
                    sl_pct_fallback = 0.35  # 0.35% SL for breakout continuation
                else:
                    tp_pct_fallback = 0.45
                    sl_pct_fallback = 0.30

                if event.side == "LONG":
                    tp_price = current_price * (1 + tp_pct_fallback / 100)
                    sl_price = current_price * (1 - sl_pct_fallback / 100)
                else:
                    tp_price = current_price * (1 - tp_pct_fallback / 100)
                    sl_price = current_price * (1 + sl_pct_fallback / 100)
                tp_sl_source = f"setup_type_fallback_{setup_type}"
                logger.debug(
                    f"📐 [FALLBACK] TP/SL generated: TP={tp_price:.4f} SL={sl_price:.4f} | Type={setup_type} | Price={current_price:.4f}"
                )
            else:
                logger.warning(
                    f"⚠️ [FALLBACK] Cannot generate TP/SL: current_price={current_price} | tp_price={tp_price} | sl_price={sl_price}"
                )

        # Phase 700 RESTORED: Simple setup-type percentage clamping (trust the structure)
        # Phase 1300: Footprint-Validated TP Expansion
        if tp_price and sl_price and current_price and current_price > 0:
            tp_pct = abs((tp_price - current_price) / current_price) * 100
            sl_pct = abs((sl_price - current_price) / current_price) * 100

            skewness = event.metadata.get("skewness", 0.5)

            # If skewness is extreme in our direction, expand TP
            if event.side == "LONG" and skewness > 0.7:
                tp_pct *= 1.0 + (skewness - 0.7) * 2.0  # Up to 60% expansion
                tp_sl_source = f"{tp_sl_source}+footprint_expansion"
            elif event.side == "SHORT" and skewness < 0.3:
                tp_pct *= 1.0 + (0.3 - skewness) * 2.0
                tp_sl_source = f"{tp_sl_source}+footprint_expansion"

            # Fix #2: Increased minimum TP to ensure RR > 1.0
            # Phase 1200: Precision Edge (Round 7) - Relax clamps for high Z-scores
            z_abs = abs(event.metadata.get("z_score", 0))

            if setup_type == "reversion":
                # If high conviction (Z > 3.5), allow wider TP and tighter SL (Sniper)
                tp_max = 1.20 if z_abs > 3.5 else 0.80

                # If FootprintDeltaDivergence is present, we can trust a tighter stop
                has_delta_div = any(
                    c.get("type") == "FootprintDeltaDivergence" for c in event.metadata.get("contributors", [])
                )

                tp_pct = max(0.35, min(tp_pct, tp_max))
                # Relax floor to 0.20% if delta validated, otherwise 0.30%
                sl_floor = 0.20 if has_delta_div else 0.30
                sl_pct = max(sl_floor, min(sl_pct, 0.45))
                tp_sl_source = f"{tp_sl_source}+reversion_edge"
                if has_delta_div:
                    tp_sl_source += "+delta_div_tight"
            elif setup_type == "continuation":
                tp_pct = max(0.40, min(tp_pct, 1.00))
                sl_pct = max(0.20, min(sl_pct, 0.50))
                tp_sl_source = f"{tp_sl_source}+continuation_clamp"
            elif setup_type == "initial":
                tp_pct = max(0.50, min(tp_pct, 1.00))
                sl_pct = max(0.25, min(sl_pct, 0.50))
                tp_sl_source = f"{tp_sl_source}+initial_clamp"
            else:
                # Generic HFT clamp
                tp_pct = max(0.30, min(tp_pct, 2.0))
                sl_pct = max(0.25, min(sl_pct, 2.0))

            # Convert back to absolute prices
            if event.side == "LONG":
                tp_price = current_price * (1 + tp_pct / 100)
                sl_price = current_price * (1 - sl_pct / 100)
            else:
                tp_price = current_price * (1 - tp_pct / 100)
                sl_price = current_price * (1 + sl_pct / 100)

        # Phase 1000: Minimum RR Enforcement (P1)
        # Phase 1200: Dynamic RR (Round 7)
        if tp_price and sl_price and current_price and current_price > 0:
            reward = abs(tp_price - current_price)
            risk = abs(sl_price - current_price)
            if risk > 0:
                rr_ratio = reward / risk
                # Phase 1300: Relax RR for reversion (Scalpingwin-rate vs RR trade-off)
                if self.fast_track:
                    rr_threshold = 0.5  # Completely bypassed for rapid testing
                elif setup_type == "reversion":
                    rr_threshold = 1.3 if z_abs > 3.5 else 1.1
                else:
                    rr_threshold = 1.5 if z_abs > 3.5 else 1.2

                if rr_ratio < rr_threshold:
                    logger.warning(
                        f"🚫 REJECTED: Low RR Ratio ({rr_ratio:.2f} < {rr_threshold}) | "
                        f"Z: {z_abs:.1f} | Symbol: {event.symbol} | Side: {event.side}"
                    )
                    return

                # Phase 1300: Dynamic RR-Based Sizing
                # Final_Bet = Base_Kelly * Clamp(RR_Ratio / 1.5, 0.5, 2.0)
                rr_multiplier = max(0.5, min(2.0, rr_ratio / 1.5))
                bet_size = base_bet_size * rr_multiplier
                sizing_method = f"{sizing_method}+RR_Sized"

        # Calculate percentage for logging (human-readable)
        tp_pct_log = abs((tp_price - current_price) / current_price) * 100 if tp_price and current_price else 0
        sl_pct_log = abs((sl_price - current_price) / current_price) * 100 if sl_price and current_price else 0

        (
            logger.info(
                f"🎯 Decision: {event.side} | {sizing_method} Bet: {bet_size:.2%} of {equity:.2f} | "
                f"Sensor: {event.selected_sensor} | Setup: {setup_type} | "
                f"TP: {tp_price:.4f} ({tp_pct_log:.2f}%) SL: {sl_price:.4f} ({sl_pct_log:.2f}%) "
                f"(Source: {tp_sl_source})"
            )
            if tp_price and sl_price
            else logger.info(
                f"🎯 Decision: {event.side} | {sizing_method} Bet: {bet_size:.2%} of {equity:.2f} | "
                f"Sensor: {event.selected_sensor} | Setup: {setup_type} | "
                f"TP/SL: config fallback (Source: {tp_sl_source})"
            )
        )

        # Phase 800: Adaptive Shadow SL (Shark Breath)
        # Structural setups need more room to breathe.
        shadow_sl_activation = 0.0045 if setup_type in ["reversion", "fade_extreme"] else 0.0025

        # Emit Decision with unique ID for tracking
        decision_id = f"DEC_{int(time.time()*1000000)}"  # Microsecond precision
        decision = DecisionEvent(
            symbol=event.symbol,
            side=event.side,
            bet_size=bet_size,
            tp_price=tp_price,
            sl_price=sl_price,
            selected_sensor=event.selected_sensor,
            t0_timestamp=getattr(event, "t0_timestamp", None),
            t1_decision_ts=getattr(event, "t1_decision_ts", None),
            trace_id=getattr(event, "trace_id", None),
            setup_type=getattr(event, "setup_type", setup_type),
            atr_1m=event.metadata.get("atr_1m", 0.0),
            timestamp=event.timestamp,
        )
        decision.decision_id = decision_id  # Add unique ID
        decision.shadow_sl_activation = shadow_sl_activation  # Phase 800

        logger.debug(f"📤 Emitting DecisionEvent {decision_id} for {event.side}")
        # Use create_task to prevent blocking signal processing loop
        asyncio.create_task(self.engine.dispatch(decision))

    def handle_trade_outcome(self, trade_id: str, won: bool):
        """Handle trade outcome (stateless)."""
        result = "WIN" if won else "LOSS"
        logger.info(f"Trade {trade_id} finished: {result}")
