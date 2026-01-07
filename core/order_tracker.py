import logging
import time
from enum import Enum
from typing import Any, Dict, Optional

from core.interfaces import TimeIterator


class ConfidenceLevel(Enum):
    LOCAL = 1  # Created locally, not yet confirmed by exchange
    WS = 2  # Confirmed via WebSocket event (Trusted)
    REST = 3  # Confirmed via REST API (Gold Standard)


class ShadowOrder:
    def __init__(self, order_data: Dict[str, Any], confidence: ConfidenceLevel):
        self.order_id = order_data.get("id") or order_data.get("orderId")
        self.symbol = order_data.get("symbol")
        self.amount = float(order_data.get("amount", 0))
        self.side = order_data.get("side")
        self.status = order_data.get("status", "open")
        self.confidence = confidence
        self.created_at = time.time()
        self.last_updated = time.time()
        self.raw_data = order_data

    def update(self, new_data: Dict[str, Any], confidence: ConfidenceLevel):
        self.status = new_data.get("status", self.status)
        self.confidence = confidence
        self.last_updated = time.time()
        self.raw_data.update(new_data)


class ShadowPosition:
    def __init__(self, symbol: str, amount: float, entry_price: float, side: str):
        self.symbol = symbol
        self.amount = amount
        self.entry_price = entry_price
        self.side = side  # LONG or SHORT
        self.last_updated = time.time()


class OrderTracker(TimeIterator):
    """
    The Authority for order states in V4.
    Replaces the old ReconciliationService by maintaining a "Shadow State".
    """

    def __init__(self, adapter: Any, probe_timeout: float = 10.0):
        self._adapter = adapter
        self._orders: Dict[str, ShadowOrder] = {}
        self._positions: Dict[str, ShadowPosition] = {}
        self._probe_timeout = probe_timeout
        self.logger = logging.getLogger("OrderTracker")
        self._active = False

    @property
    def name(self) -> str:
        return "OrderTracker"

    async def start(self) -> None:
        self._active = True
        self.logger.info("🛡️ OrderTracker (Shadow State) started")

    async def stop(self) -> None:
        self._active = False
        self.logger.info("🛑 OrderTracker stopped")

    def track_local_order(self, order_data: Dict[str, Any]):
        """Register an order just sent to the exchange."""
        oid = order_data.get("id") or order_data.get("orderId")
        if not oid:
            self.logger.error("Attempted to track order without ID")
            return

        shadow = ShadowOrder(order_data, ConfidenceLevel.LOCAL)
        self._orders[oid] = shadow
        self.logger.info(f"📝 Tracking LOCAL order: {oid} ({shadow.symbol})")

    async def handle_ws_update(self, event: Dict[str, Any]):
        """Update state from WebSocket event (High Trust)."""
        oid = event.get("id") or event.get("orderId")
        if oid in self._orders:
            order = self._orders[oid]
            order.update(event, ConfidenceLevel.WS)
            self.logger.info(f"⚡ WS Update for {oid}: {order.status}")

            # Position tracking logic
            if order.status in ["closed", "FILLED"]:
                self._update_position_from_order(order)

        else:
            # Ghost order detected via WS?
            shadow = ShadowOrder(event, ConfidenceLevel.WS)
            self._orders[oid] = shadow
            self.logger.warning(f"👻 Detected un-tracked order via WS: {oid}")
            if shadow.status in ["closed", "FILLED"]:
                self._update_position_from_order(shadow)

    def _update_position_from_order(self, order: ShadowOrder):
        """Derive position changes from filled orders."""
        symbol = order.symbol
        side = order.side  # buy or sell
        amount = order.amount
        price = float(order.raw_data.get("price", 0)) or float(order.raw_data.get("average", 0))

        if symbol not in self._positions:
            # New position
            pos_side = "LONG" if side == "buy" else "SHORT"
            self._positions[symbol] = ShadowPosition(symbol, amount, price, pos_side)
            self.logger.info(f"📈 ShadowPosition NEW: {symbol} {pos_side} {amount}")
        else:
            pos = self._positions[symbol]
            # Simple net-position logic (for single-position symbols)
            if (pos.side == "LONG" and side == "buy") or (pos.side == "SHORT" and side == "sell"):
                # Increasing position
                new_amount = pos.amount + amount
                # WAP (Weighted Average Price) calculation simplified
                if new_amount > 0:
                    pos.entry_price = (pos.entry_price * pos.amount + price * amount) / new_amount
                pos.amount = new_amount
            else:
                # Decreasing or flipping position
                new_amount = pos.amount - amount
                if new_amount > 0.00001:  # Margin for floating point
                    pos.amount = new_amount
                elif new_amount < -0.00001:
                    # Flipped
                    pos.side = "SHORT" if pos.side == "LONG" else "LONG"
                    pos.amount = abs(new_amount)
                    pos.entry_price = price
                else:
                    # Closed
                    del self._positions[symbol]
                    self.logger.info(f"📉 ShadowPosition CLOSED: {symbol}")
                    return

            self.logger.info(f"🔄 ShadowPosition UPDATED: {symbol} {pos.side} {pos.amount}")

    async def tick(self, timestamp: float) -> None:
        """
        Audit stale orders.
        If an order in LOCAL confidence has no update for > probe_timeout,
        trigger a surgical REST poll.
        """
        if not self._active:
            return

        now = time.time()
        ids_to_probe = []

        for oid, order in self._orders.items():
            if order.confidence == ConfidenceLevel.LOCAL:
                if now - order.created_at > self._probe_timeout:
                    ids_to_probe.append(oid)

        for oid in ids_to_probe:
            await self._probe_order(oid)

        # Periodic Deep Sync (Optional safety)
        if int(timestamp) % 1800 == 0:  # Every 30 mins
            await self.deep_sync_positions()

    async def deep_sync_positions(self):
        """
        Reconcile shadow positions with the exchange (The Gold Standard check).
        Replaces the old ReconciliationService loop.
        """
        self.logger.info("🕵️ Starting Deep Position Sync (Auditing Shadow State)...")
        try:
            exchange_positions = await self._adapter.fetch_positions()

            # 1. Map exchange positions by symbol
            ex_pos_map = {p["symbol"]: p for p in exchange_positions if float(p.get("contracts", 0)) != 0}

            # Phase 16 Legacy: GLITCH SAFETY VALVE
            local_count = len(self._positions)
            exchange_count = len(ex_pos_map)
            GLITCH_THRESHOLD = 5

            if local_count > GLITCH_THRESHOLD and exchange_count == 0:
                self.logger.critical(
                    f"🚨 MASS DETACHMENT DETECTED: Shadow has {local_count} positions, Exchange has 0. "
                    "Aborting Deep Sync for safety."
                )
                return

            # 2. Reconcile with Shadow State
            all_symbols = set(list(self._positions.keys()) + list(ex_pos_map.keys()))

            for symbol in all_symbols:
                local_pos = self._positions.get(symbol)
                remote_pos = ex_pos_map.get(symbol)

                if local_pos and not remote_pos:
                    # GHOST DETECTED: We think we have it, exchange says no.
                    # In V4, we trust the Exchange as the Gold Standard for positions.
                    self.logger.warning(
                        f"👻 DISCREPANCY: Shadow thinks {symbol} is open, but Exchange says no. Cleaning up..."
                    )
                    del self._positions[symbol]

                elif remote_pos and not local_pos:
                    # ORPHAN DETECTED: Exchange has it, we don't.
                    self.logger.warning(f"🛸 DISCREPANCY: Exchange has {symbol} but Shadow missed it. Recovering...")
                    # Recover state from remote
                    side = "LONG" if float(remote_pos.get("contracts", 0)) > 0 else "SHORT"
                    pos_amount = abs(float(remote_pos["contracts"]))
                    entry_p = float(remote_pos["entryPrice"])

                    self._positions[symbol] = ShadowPosition(symbol, pos_amount, entry_p, side)

                    # Bridge to Historian: Record the adoption for accounting transparency
                    from core.observability.historian import historian

                    historian.record_external_closure(
                        symbol=symbol,
                        side=side,
                        qty=pos_amount,
                        entry_price=entry_p,
                        exit_price=entry_p,  # Use entry as exit for adoption trace
                        reason="ADOPTED",
                        session_id=getattr(self._adapter, "session_id", "V4_RECOVERY"),
                    )

                elif local_pos and remote_pos:
                    # Both agree it exists, check amount
                    diff = abs(local_pos.amount - abs(float(remote_pos["contracts"])))
                    if diff > 0.00001:
                        self.logger.warning(
                            f"📏 DISCREPANCY: {symbol} amount mismatch. Shadow: {local_pos.amount}, Remote: {abs(float(remote_pos['contracts']))}. Fixing..."
                        )
                        local_pos.amount = abs(float(remote_pos["contracts"]))

            self.logger.info("✅ Deep Sync Complete. Shadow State is now REST-aligned.")

        except Exception as e:
            self.logger.error(f"❌ Failed to perform Deep Sync: {e}")

    async def _probe_order(self, order_id: str):
        """Perform surgical REST poll for a specific stale order."""
        order = self._orders.get(order_id)
        if not order:
            return

        self.logger.warning(f"🔍 Probing stale LOCAL order: {order_id}...")
        try:
            # Surgical poll via adapter
            remote_order = await self._adapter.fetch_order(order_id, order.symbol)
            if remote_order:
                order.update(remote_order, ConfidenceLevel.REST)
                self.logger.info(f"✅ Probe success for {order_id}: {order.status} (RESTized)")
            else:
                self.logger.error(f"❌ Probe FAILED for {order_id}: Not found on exchange.")
                # Decision: Mark as orphaned or remove?
                # For now, mark as ERROR/UNKNOWN or keep tracking.
        except Exception as e:
            self.logger.error(f"❌ Error during order probe for {order_id}: {e}")

    def get_active_orders(self, symbol: Optional[str] = None) -> Dict[str, ShadowOrder]:
        """Return all orders that are not closed/canceled."""
        return {
            oid: o
            for oid, o in self._orders.items()
            if (not symbol or o.symbol == symbol)
            and o.status not in ["closed", "canceled", "rejected", "FILLED", "CANCELED"]
        }
