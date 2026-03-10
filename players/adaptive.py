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

from core.events import Event, EventType
from decision.aggregator import AggregatedSignalEvent
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
    ):
        super().__init__(type=EventType.DECISION, timestamp=time.time())
        self.t0_timestamp = t0_timestamp
        self.t1_decision_ts = t1_decision_ts
        self.trace_id = trace_id
        self.symbol = symbol
        self.side = side
        self.bet_size = bet_size
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.tp_price = tp_price  # Absolute TP price (primary)
        self.sl_price = sl_price  # Absolute SL price (primary)
        self.selected_sensor = selected_sensor
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

        if tp_price and sl_price:
            return tp_price, sl_price

        return None, None

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

        # Phase 800: Unified TP/SL pipeline — absolute prices are primary
        tp_price = None
        sl_price = None

        setup_type = event.metadata.get("setup_type", "unknown")
        tp_sl_source = "config_fallback"

        # Phase 700: Structural TP/SL from HTF levels (Trader Dale Ready)
        htf_levels = self._get_best_htf_levels(event.metadata or {})
        current_price = event.metadata.get("price")

        if htf_levels and current_price and current_price > 0:
            struct_tp, struct_sl = self._calculate_structural_tp_sl(
                event.side, current_price, htf_levels, setup_type, regime=regime
            )
            if struct_tp is not None and struct_sl is not None:
                tp_price = struct_tp
                sl_price = struct_sl
                tp_sl_source = f"structural_{htf_levels['source_tf']}"
                logger.debug(
                    f"🎯 Structural TP/SL from {htf_levels['source_tf']}: "
                    f"TP={tp_price:.4f} SL={sl_price:.4f} | "
                    f"POC={htf_levels['poc']:.4f} VAH={htf_levels['vah']:.4f} VAL={htf_levels['val']:.4f}"
                )

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
                    if current_price <= poc:
                        tp_price = poc if (poc - current_price) / current_price > 0.001 else vah
                    sl_price = val * 0.999  # Just below VAL

                elif event.side == "SHORT":
                    if current_price >= poc:
                        tp_price = poc if (current_price - poc) / current_price > 0.001 else val
                    sl_price = vah * 1.001  # Just above VAH

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
                        tp_price = target["price"]
                        logger.debug(f"🎯 Unfinished Business TARGET: Override TP to {tp_price:.4f}")
                        tp_sl_source = "unfinished_business"

        # Phase 800: PERCENT_PRICE guard on absolute prices
        # Binance rejects limit orders too far from current market price (-4131).
        # Clamp TP/SL within 2% max distance from entry, and minimum 0.1% to avoid -2021.
        MAX_DISTANCE_PCT = 0.02  # 2% max distance from entry
        MIN_DISTANCE_PCT = 0.001  # 0.1% min distance from entry

        if tp_price and current_price and current_price > 0:
            # 1. Check Max Distance
            max_tp_dist = current_price * MAX_DISTANCE_PCT
            if abs(tp_price - current_price) > max_tp_dist:
                if event.side == "LONG":
                    tp_price = current_price + max_tp_dist
                else:
                    tp_price = current_price - max_tp_dist
                tp_sl_source = f"{tp_sl_source}+clamped_max"
                logger.debug(f"⚠️ TP clamped to max {MAX_DISTANCE_PCT:.0%} distance: {tp_price:.4f}")

            # 2. Check Min Distance (-2021 Prevention)
            min_tp_dist = current_price * MIN_DISTANCE_PCT
            if abs(tp_price - current_price) < min_tp_dist:
                if event.side == "LONG":
                    tp_price = current_price + min_tp_dist
                else:
                    tp_price = current_price - min_tp_dist
                tp_sl_source = f"{tp_sl_source}+clamped_min"
                logger.debug(f"⚠️ TP clamped to MIN {MIN_DISTANCE_PCT:.1%} distance: {tp_price:.4f}")

        if sl_price and current_price and current_price > 0:
            # 1. Check Max Distance
            max_sl_dist = current_price * 0.01  # 1% max SL distance
            if abs(sl_price - current_price) > max_sl_dist:
                if event.side == "LONG":
                    sl_price = current_price - max_sl_dist
                else:
                    sl_price = current_price + max_sl_dist
                logger.debug(f"⚠️ SL clamped to max 1% distance: {sl_price:.4f}")

            # 2. Check Min Distance (-2021 Prevention)
            min_sl_dist = current_price * MIN_DISTANCE_PCT
            if abs(sl_price - current_price) < min_sl_dist:
                if event.side == "LONG":
                    sl_price = current_price - min_sl_dist
                else:
                    sl_price = current_price + min_sl_dist
                logger.debug(f"⚠️ SL clamped to MIN {MIN_DISTANCE_PCT:.1%} distance: {sl_price:.4f}")

        # Phase 650.3: Order Book Confirmation Confidence
        dom_confirmed = event.metadata.get("dom_wall_confirmed", False)
        if dom_confirmed and bet_size:
            bet_size = min(bet_size * 2.0, self.kelly_max if self.use_kelly else self.fixed_pct * 3.0)
            logger.debug(f"🧱 [Phase 650] Massive DOM Wall confirmed absorption! Doubling bet size to {bet_size:.2%}")

        # Phase 600: Trader Dale Absorption Sizing
        intensity = event.metadata.get("absorption_intensity", 1.0)
        if intensity > 3.0 and bet_size:
            # Highly asymmetric absorption -> slightly increase bet size confidence
            bet_size = min(bet_size * 1.5, self.kelly_max if self.use_kelly else self.fixed_pct * 2.0)

        # Calculate percentage for logging (human-readable)
        tp_pct_log = abs((tp_price - current_price) / current_price) * 100 if tp_price and current_price else 0
        sl_pct_log = abs((sl_price - current_price) / current_price) * 100 if sl_price and current_price else 0

        (
            logger.info(
                f"🎯 Decision: {event.side} | {sizing_method} Bet: {bet_size:.2%} of {equity:.2f} | "
                f"Sensor: {event.selected_sensor} | Setup: {setup_type} | "
                f"TP: {tp_price:.4f} ({tp_pct_log:.2f}%) SL: {sl_price:.4f} ({sl_pct_log:.2f}%) "
                f"(Source: {tp_sl_source}, Intensity: {intensity})"
            )
            if tp_price and sl_price
            else logger.info(
                f"🎯 Decision: {event.side} | {sizing_method} Bet: {bet_size:.2%} of {equity:.2f} | "
                f"Sensor: {event.selected_sensor} | Setup: {setup_type} | "
                f"TP/SL: config fallback (Source: {tp_sl_source}, Intensity: {intensity})"
            )
        )

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
        )
        decision.decision_id = decision_id  # Add unique ID
        logger.debug(f"📤 Emitting DecisionEvent {decision_id} for {event.side}")
        # Use create_task to prevent blocking signal processing loop
        asyncio.create_task(self.engine.dispatch(decision))

    def handle_trade_outcome(self, trade_id: str, won: bool):
        """Handle trade outcome (stateless)."""
        result = "WIN" if won else "LOSS"
        logger.info(f"Trade {trade_id} finished: {result}")
