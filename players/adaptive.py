"""
Fixed Player Strategy
=====================

A simple player that bets a fixed percentage of equity on every signal.
Supports optional Kelly Criterion sizing based on sensor performance.
"""

import asyncio
import logging
import time

from core.events import Event, EventType
from decision.aggregator import AggregatedSignalEvent
from decision.sensor_tracker import SensorTracker

logger = logging.getLogger(__name__)


class DecisionEvent(Event):
    """Decision event with bet sizing."""

    def __init__(
        self,
        symbol: str,
        side: str,
        bet_size: float,
        tp_pct: float = None,
        sl_pct: float = None,
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

    def _calculate_structural_tp_sl(self, side: str, entry_price: float, htf_levels: dict, setup_type: str) -> tuple:
        """
        Phase 700: Calculate TP/SL based on structural levels.

        Returns (tp_pct, sl_pct) or (None, None) if levels invalid.
        """
        poc = htf_levels.get("poc")
        vah = htf_levels.get("vah")
        val = htf_levels.get("val")

        if not all([poc, vah, val]) or entry_price <= 0:
            return None, None

        tp_price = None
        sl_price = None

        if setup_type == "reversion":
            # Reversion: target POC from VAH/VAL
            if side == "LONG" and entry_price <= val * 1.001:
                # Entering near VAL, target POC
                tp_price = poc
                sl_price = val * 0.998  # Just below VAL
            elif side == "SHORT" and entry_price >= vah * 0.999:
                # Entering near VAH, target POC
                tp_price = poc
                sl_price = vah * 1.002  # Just above VAH

        elif setup_type == "initial":
            # Initial breakout: target VA boundary
            if side == "LONG":
                tp_price = vah
                sl_price = entry_price * 0.998  # Tight SL for breakout
            else:
                tp_price = val
                sl_price = entry_price * 1.002

        elif setup_type == "continuation":
            # Continuation: target VA boundary, SL behind POC
            if side == "LONG":
                tp_price = vah
                sl_price = poc * 0.999
            else:
                tp_price = val
                sl_price = poc * 1.001

        if tp_price and sl_price:
            tp_pct = abs((tp_price - entry_price) / entry_price) * 100
            sl_pct = abs((sl_price - entry_price) / entry_price) * 100
            return tp_pct, sl_pct

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

        # Extract TP/SL from metadata if available (Dynamic Exits Phase 600)
        tp_pct = event.metadata.get("tp_pct")
        sl_pct = event.metadata.get("sl_pct")

        setup_type = event.metadata.get("setup_type", "unknown")
        tp_sl_source = "sensor_config"

        # Phase 700: Structural TP/SL from HTF levels (Trader Dale Ready)
        htf_levels = self._get_best_htf_levels(event.metadata or {})
        current_price = event.metadata.get("price")

        if htf_levels and current_price and current_price > 0:
            struct_tp, struct_sl = self._calculate_structural_tp_sl(event.side, current_price, htf_levels, setup_type)
            if struct_tp is not None and struct_sl is not None:
                tp_pct = struct_tp
                sl_pct = struct_sl
                tp_sl_source = f"structural_{htf_levels['source_tf']}"
                logger.debug(
                    f"🎯 Structural TP/SL from {htf_levels['source_tf']}: "
                    f"TP={tp_pct:.3f}% SL={sl_pct:.3f}% | "
                    f"POC={htf_levels['poc']:.4f} VAH={htf_levels['vah']:.4f} VAL={htf_levels['val']:.4f}"
                )

        # Phase 600: James Dalton Contextual Exits (fallback if no HTF levels)
        if "poc" in event.metadata and "vah" in event.metadata and "val" in event.metadata:
            # We have Market Profile data
            poc = event.metadata["poc"]
            vah = event.metadata["vah"]
            val = event.metadata["val"]
            current_price = event.metadata.get("price")  # We need price. If missing, we skip dynamic calc

            # Rough estimation if current_price not explicitly in metadata: use the signal price or assume tight spread
            # Best practice is for sensor to pass current price. Let's assume we have it or we can't calculate a relative %
            if not current_price and "price" in event.metadata:
                current_price = event.metadata["price"]

            if current_price and current_price > 0:
                tp_sl_source = "dalton_context"
                if event.side == "LONG":
                    # If entering a LONG near or below VAL, target the POC or VAH
                    if current_price <= poc:
                        # Target POC if below POC, VAH if near POC
                        target_price = poc if (poc - current_price) / current_price > 0.001 else vah
                        tp_pct = ((target_price - current_price) / current_price) * 100

                    # Stop loss tightly below VAL if entering near VAL
                    sl_target = val * 0.999  # Just below VAL
                    calc_sl = ((current_price - sl_target) / current_price) * 100
                    if calc_sl > 0:
                        sl_pct = calc_sl

                elif event.side == "SHORT":
                    # If entering a SHORT near or above VAH, target POC or VAL
                    if current_price >= poc:
                        target_price = poc if (current_price - poc) / current_price > 0.001 else val
                        tp_pct = ((current_price - target_price) / current_price) * 100

                    # Stop loss tightly above VAH
                    sl_target = vah * 1.001
                    calc_sl = ((sl_target - current_price) / current_price) * 100
                    if calc_sl > 0:
                        sl_pct = calc_sl

                # Ensure minimum logical TP/SLs for HFT
                if tp_pct is not None:
                    tp_pct = max(0.1, min(tp_pct, 2.0))
                if sl_pct is not None:
                    sl_pct = max(0.25, min(sl_pct, 2.0))

        # Phase 3: Setup-type specific TP/SL shaping
        # Keep conservative defaults; only clamp/shape if we have values.
        if setup_type == "reversion":
            # Reversion scalps: tighter TP/SL to reduce time-in-trade and avoid trend steamroll.
            if tp_pct is not None:
                tp_pct = max(0.10, min(tp_pct, 0.60))
            if sl_pct is not None:
                sl_pct = max(0.15, min(sl_pct, 0.45))
            tp_sl_source = f"{tp_sl_source}+reversion_clamp"
        elif setup_type == "continuation":
            # Continuation: allow a bit more room on TP, keep SL tight-ish.
            if tp_pct is not None:
                tp_pct = max(0.15, min(tp_pct, 0.90))
            if sl_pct is not None:
                sl_pct = max(0.15, min(sl_pct, 0.55))
            tp_sl_source = f"{tp_sl_source}+continuation_clamp"
        elif setup_type == "initial":
            # Initial breakout (FootprintStackedImbalance new stack): wider SL for entry volatility.
            # Breakouts can have false starts; give more room while keeping TP reasonable.
            if tp_pct is not None:
                tp_pct = max(0.20, min(tp_pct, 0.80))
            if sl_pct is not None:
                sl_pct = max(0.20, min(sl_pct, 0.50))
            tp_sl_source = f"{tp_sl_source}+initial_clamp"

        # Phase 650.2: Unfinished Business Exact Targeting
        unfinished_targets = event.metadata.get("unfinished_business_targets", [])
        if unfinished_targets and current_price and current_price > 0:
            for target in unfinished_targets:
                if event.side == "LONG" and target.get("side") == "LONG_TARGET":
                    calc_tp = ((target["price"] - current_price) / current_price) * 100
                    if calc_tp > 0.05:  # ensure it's at least a few ticks away
                        tp_pct = calc_tp
                        logger.debug(
                            f"🎯 [Phase 650] Overriding TP to Unfinished Business at {target['price']} ({tp_pct:.2f}%)"
                        )
                elif event.side == "SHORT" and target.get("side") == "SHORT_TARGET":
                    calc_tp = ((current_price - target["price"]) / current_price) * 100
                    if calc_tp > 0.05:
                        tp_pct = calc_tp
                        logger.debug(
                            f"🎯 [Phase 650] Overriding TP to Unfinished Business at {target['price']} ({tp_pct:.2f}%)"
                        )

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

        logger.info(
            f"🎯 Decision: {event.side} | {sizing_method} Bet: {bet_size:.2%} of {equity:.2f} | "
            f"Sensor: {event.selected_sensor} | Setup: {setup_type} | TP: {tp_pct}% SL: {sl_pct}% "
            f"(TP/SL: {tp_sl_source}, Intensity: {intensity})"
        )

        # Emit Decision with unique ID for tracking
        decision_id = f"DEC_{int(time.time()*1000000)}"  # Microsecond precision
        decision = DecisionEvent(
            symbol=event.symbol,
            side=event.side,
            bet_size=bet_size,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
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
