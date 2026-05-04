"""
Fixed Player Strategy
=====================

A simple player that bets a fixed percentage of equity on every signal.
Supports optional Kelly Criterion sizing based on sensor performance.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.events import AggregatedSignalEvent, Event, EventType
from decision.sensor_tracker import SensorTracker

logger = logging.getLogger(__name__)


@dataclass
class DecisionEvent(Event):
    """Decision event with bet sizing and absolute TP/SL prices."""

    type: EventType = EventType.DECISION
    timestamp: float = field(default_factory=time.time)
    symbol: str = ""
    side: str = ""
    bet_size: float = 0.0
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    selected_sensor: Optional[str] = None
    t0_timestamp: Optional[float] = None
    t1_decision_ts: Optional[float] = None
    trace_id: Optional[str] = None
    setup_type: str = "unknown"
    atr_1m: float = 0.0
    # Phase 880: Structural metadata for Auction Invalidation
    trigger_level: Optional[float] = None
    trigger_type: Optional[str] = "unknown"
    initial_narrative: Optional[Dict[str, Any]] = None
    fast_track: bool = False

    def __post_init__(self):
        # Ensure type is always DECISION even if passed otherwise
        self.type = EventType.DECISION


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

    # Phase 600: Refactored - Structural TP/SL is now handled EXCLUSIVELY by the SetupEngine.
    # The Player is a "Dumb Executor" that trusts the Footprint-calculated targets.

    async def on_aggregated_signal(self, event: AggregatedSignalEvent):
        """Process aggregated signal and place bet."""
        import config.trading as trading_config

        if getattr(trading_config, "AUDIT_MODE", False):
            logger.debug(f"🔍 Audit Mode: Signal {event.setup_type} (ignored by player)")
            return

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
        setup_type = getattr(event, "setup_type", event.metadata.get("setup_type", "unknown"))
        current_price = event.metadata.get("price")

        # Phase 970: Dumb Execution Layer (Absolute Order Flow Trust)
        # The AdaptivePlayer is no longer responsible for guessing exits.
        # It strictly executes the precise geometrical TP/SL calculated by the SetupEngine.
        tp_price = event.metadata.get("tp_price")
        sl_price = event.metadata.get("sl_price")

        if tp_price is None or sl_price is None:
            logger.warning(
                f"🚫 Signal {setup_type} REJECTED: Missing structural TP/SL. "
                f"LTA V4 requires absolute targets from SetupEngine."
            )
            return

        tp_sl_source = "setup_engine_structural_anchor"

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

        # Phase 700: Structural Validation (replace old clamps with RR + sanity checks)
        if tp_price and sl_price and current_price and current_price > 0:
            # Sanity: TP must be in the right direction
            if event.side == "LONG" and (tp_price <= current_price or sl_price >= current_price):
                logger.warning(
                    f"🚫 REJECTED: Inverted TP/SL for LONG | TP={tp_price:.4f} SL={sl_price:.4f} Price={current_price:.4f}"
                )
                return
            elif event.side == "SHORT" and (tp_price >= current_price or sl_price <= current_price):
                logger.warning(
                    f"🚫 REJECTED: Inverted TP/SL for SHORT | TP={tp_price:.4f} SL={sl_price:.4f} Price={current_price:.4f}"
                )
                return

            # Max distance sanity (> 10% is not scalping)
            tp_dist = abs(tp_price - current_price) / current_price * 100
            sl_dist = abs(sl_price - current_price) / current_price * 100
            if tp_dist > 10.0 or sl_dist > 10.0:
                logger.warning(f"🚫 REJECTED: Distance too large (TP={tp_dist:.2f}% SL={sl_dist:.2f}%)")
                return

            reward = abs(tp_price - current_price)
            risk = abs(sl_price - current_price)
            if risk > 0:
                rr_ratio = reward / risk

                # Phase 700: Simple RR validation — trust the structure
                if rr_ratio < 1.0:
                    logger.warning(
                        f"🚫 REJECTED: Low RR Ratio ({rr_ratio:.2f} < 1.0) | "
                        f"Symbol: {event.symbol} | Side: {event.side}"
                    )
                    return

                # RR-Based Sizing (keep from Phase 1300)
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

        # Phase 800/870: Adaptive Shadow SL (Shark Breath)
        # Structural setups need more room to breathe, but high z-scores need tighter exits.
        base_activation = 0.0075 if setup_type in ["reversion", "fade_extreme"] else 0.0045
        z_score = abs(event.metadata.get("z_score") or 3.0)
        # Multiplier: as Z increases, activation DECREASES (tighter).
        # Scale: Z=3.0 -> mult=0.7, Z=5.0 -> mult=0.5, Z=1.0 -> mult=0.9
        activation_multiplier = max(0.5, min(1.2, 1.0 - (z_score / 10.0)))
        shadow_sl_activation = base_activation * activation_multiplier

        # Emit Decision with unique ID for tracking
        decision_id = f"DEC_{int(time.time()*1000000)}"  # Microsecond precision

        # Phase 85: Finalize T1 (Decision Time)
        t1_ts = getattr(event, "t1_decision_ts", None) or time.time()

        decision = DecisionEvent(
            symbol=event.symbol,
            side=event.side,
            bet_size=bet_size,
            tp_price=tp_price,
            sl_price=sl_price,
            selected_sensor=event.selected_sensor,
            t0_timestamp=getattr(event, "t0_timestamp", event.timestamp),
            t1_decision_ts=t1_ts,
            trace_id=getattr(event, "trace_id", None),
            setup_type=getattr(event, "setup_type", setup_type),
            atr_1m=event.metadata.get("atr_1m", 0.0),
            timestamp=event.timestamp,
            trigger_level=event.metadata.get("level_price") or event.metadata.get("poc"),
            trigger_type=event.metadata.get("pattern", "unknown"),
            initial_narrative={
                "poc": event.metadata.get("poc"),
                "vah": event.metadata.get("vah"),
                "val": event.metadata.get("val"),
                "z_score": event.metadata.get("z_score"),
            },
            fast_track=self.fast_track,
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
