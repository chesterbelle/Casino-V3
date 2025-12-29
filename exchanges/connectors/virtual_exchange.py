"""
Virtual Exchange Connector - Casino V3

A self-contained simulated exchange that mimics the behavior of a real exchange
(like Binance or Kraken) but runs locally in memory.

It is designed to be used by BacktestDataSource to provide a realistic
trading environment that is identical to the Live/Demo environment from
the perspective of the TradingSession and Croupier.
"""

import logging
from typing import Any, Dict, List, Optional

from exchanges.connectors.connector_base import BaseConnector


class VirtualExchangeConnector(BaseConnector):
    """
    Virtual Exchange that simulates a real crypto exchange.

    Features:
    - Maintains internal order book and account balance
    - Simulates order execution (Market, Limit, Stop, Take Profit)
    - Tracks positions and calculates PnL
    - Supports OCO-like behavior via conditional orders
    - Realistic fee and slippage simulation
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        fee_rate: float = 0.0006,  # 0.06% (Taker)
        maker_fee_rate: float = 0.0002,  # 0.02% (Maker)
        slippage_rate: float = 0.0001,  # 0.01%
        simulation_spread: float = 0.0005,  # 0.05% (Spread simulation)
        min_amount: float = 0.001,
        amount_precision: int = 3,
    ):
        self.logger = logging.getLogger("VirtualExchange")

        # Configuration
        self.initial_balance = initial_balance
        self.fee_rate = fee_rate
        self.maker_fee_rate = maker_fee_rate
        self.slippage_rate = slippage_rate
        self.simulation_spread = simulation_spread
        self.min_amount = min_amount
        self.amount_precision = amount_precision
        self.base_currency = "USD"

        # State
        self._balance = initial_balance
        self._orders: Dict[str, Dict] = {}  # id -> order
        self._positions: List[Dict] = []  # list of position dicts
        self._trades: List[Dict] = []  # history of trades

        self._current_price: float = 0.0
        self._current_timestamp: int = 0
        self._order_seq = 0

        self._connected = False
        self._ready = False

        # OCO pair tracking: {order_id: sibling_order_id}
        self._oco_pairs: Dict[str, str] = {}

        # Order update callback (like Binance WebSocket)
        self._order_update_callback = None

        self.logger.info(
            f"🏦 VirtualExchange initialized | Balance: ${initial_balance:,.2f} | "
            f"Fee: {fee_rate:.2%} | Slippage: {slippage_rate:.2%}"
        )

    # =========================================================
    # 🔌 CONNECTION MANAGEMENT
    # =========================================================

    async def connect(self) -> None:
        """Simulate connection."""
        self._connected = True
        self._ready = True
        self.logger.info("✅ VirtualExchange connected")

    async def close(self) -> None:
        """Simulate disconnection."""
        self._connected = False
        self._ready = False
        self.logger.info("🔌 VirtualExchange disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def exchange_name(self) -> str:
        return "VirtualExchange"

    def set_order_update_callback(self, callback):
        """Register a callback for order updates (like Binance WebSocket)."""
        self._order_update_callback = callback

    async def register_oco_pair(self, symbol: str, tp_order_id: str, sl_order_id: str):
        """
        Register TP and SL orders as an OCO pair.
        When one fills, the other will be cancelled.
        """
        self._oco_pairs[tp_order_id] = sl_order_id
        self._oco_pairs[sl_order_id] = tp_order_id
        self.logger.info(f"🔗 OCO pair registered: TP={tp_order_id} <-> SL={sl_order_id}")

    def price_to_precision(self, symbol: str, price: float) -> str:
        """Format price to symbol precision (simplified)."""
        return f"{price:.2f}"

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Format amount to symbol precision."""
        return str(round(amount, self.amount_precision))

    # =========================================================
    # ⚙️ ENGINE (The "Virtual" part)
    # =========================================================

    def process_tick(self, tick: Dict[str, Any]) -> None:
        """
        Update state with a single tick and check for fills.

        Args:
            tick: Dict with 'price', 'timestamp'
        """
        self._current_timestamp = int(tick["timestamp"])
        price = float(tick["price"])
        self._current_price = price

        # Check fills against this specific price
        # We treat High/Low as the same (current price) for a tick
        for order_id, order in list(self._orders.items()):
            if order["status"] != "open":
                continue
            self._process_order(order, high=price, low=price)

    def update_market_state(self, candle: Dict[str, Any]) -> None:
        """
        Legacy: Update with candle.
        """
        self._current_timestamp = int(candle["timestamp"])
        self._current_price = float(candle["close"])
        high = float(candle["high"])
        low = float(candle["low"])

        for order_id, order in list(self._orders.items()):
            if order["status"] != "open":
                continue
            self._process_order(order, high, low)

    def _process_order(self, order: Dict, high: float, low: float) -> None:
        """Check if an order should be triggered/filled based on price action."""
        side = order["side"]
        order_type = order["type"]
        stop_price = order.get("stopPrice")
        price = order.get("price")  # Limit price

        triggered = False
        execution_price = 0.0

        # 1. Check Triggers (Stop Loss / Take Profit)
        if stop_price:
            # STOP/TAKE_PROFIT orders become Market orders when triggered
            # For BUY: trigger if price >= stopPrice (Stop Buy) or price <= stopPrice (Take Profit Buy?)
            # Context: Usually Stop Loss Sell is below price, Take Profit Sell is above.
            # But here we use generic "stopPrice".
            # Convention:
            #   - If side=SELL and stopPrice < current: Stop Loss (trigger if Low <= stopPrice)
            #   - If side=SELL and stopPrice > current: Take Profit (trigger if High >= stopPrice)
            #   - If side=BUY and stopPrice > current: Stop Buy (trigger if High >= stopPrice)
            #   - If side=BUY and stopPrice < current: Take Profit (trigger if Low <= stopPrice)

            # Simplified logic based on standard exchange behavior:
            # We assume the order was placed correctly relative to price.

            # Spread simulation: Always trade against the spread
            # SELL orders execute at BID (Price - Spread)
            # BUY orders execute at ASK (Price + Spread)

            spread_val = stop_price * self.simulation_spread

            # Calculate effective candle range for execution
            bid_high = high - spread_val
            bid_low = low - spread_val
            ask_high = high + spread_val
            ask_low = low + spread_val

            if side == "sell":
                # SELL STOP logic
                # We need to determine if this is a Stop Loss (trigger on drop) or Take Profit (trigger on rise)
                # Since we don't track the intent, we check both possibilities relative to the range

                # Case A: Price drops to stop (SL behavior) -> Check Bid Low
                if bid_low <= stop_price <= self._current_price:
                    triggered = True
                    execution_price = stop_price

                # Case B: Price rises to stop (TP behavior) -> Check Bid High
                elif self._current_price <= stop_price <= bid_high:
                    triggered = True
                    execution_price = stop_price

                # Case C: Candle fully engulfs stop (Gap)
                elif bid_low <= stop_price <= bid_high:
                    triggered = True
                    execution_price = stop_price

            else:  # buy
                # BUY STOP logic

                # Case A: Price rises to stop (SL for Short) -> Check Ask High
                if self._current_price <= stop_price <= ask_high:
                    triggered = True
                    execution_price = stop_price

                # Case B: Price drops to stop (TP for Short) -> Check Ask Low
                elif ask_low <= stop_price <= self._current_price:
                    triggered = True
                    execution_price = stop_price

                # Case C: Candle fully engulfs
                elif ask_low <= stop_price <= ask_high:
                    triggered = True
                    execution_price = stop_price

        # 2. Check Limit Orders
        elif order_type == "limit":
            limit_price = price
            if side == "buy":
                # Buy limit: fill if Low <= limit_price
                if low <= limit_price:
                    triggered = True
                    execution_price = limit_price  # Limit guarantees price or better
            else:  # sell
                # Sell limit: fill if High >= limit_price
                if high >= limit_price:
                    triggered = True
                    execution_price = limit_price

        if triggered:
            self._execute_order_fill(order, execution_price)

    def _execute_order_fill(self, order: Dict, price: float) -> None:
        """Execute the fill of an order."""
        # Apply slippage for stop/market orders (not limit)
        is_limit = order["type"] == "limit"

        if not is_limit:
            if order["side"] == "buy":
                price = price * (1 + self.slippage_rate)
            else:
                price = price * (1 - self.slippage_rate)

        # Calculate fee
        # Maker fee for limit orders, Taker for others
        fee_rate = self.maker_fee_rate if is_limit else self.fee_rate
        amount = order["amount"]
        notional = amount * price
        fee_cost = notional * fee_rate

        # Update Order
        order["status"] = "closed"
        order["filled"] = amount
        order["remaining"] = 0.0
        order["price"] = price  # Avg fill price
        order["cost"] = notional
        order["fee"] = {"cost": fee_cost, "currency": self.base_currency}
        order["closed_timestamp"] = self._current_timestamp

        # Update Balance & Positions
        self._update_account_state(order)

        self.logger.info(
            f"⚡ Order filled (Virtual) | {order['side'].upper()} {amount} @ {price:.2f} | "
            f"Fee: {fee_cost:.4f} | PnL: {order.get('realized_pnl', 0):.2f}"
        )

        # Handle OCO-like behavior (cancel siblings)
        self._cancel_siblings(order)

        # Notify order update callback (like Binance WebSocket)
        if self._order_update_callback:
            try:
                normalized = self._normalize_order(order)
                self._order_update_callback(normalized)
            except Exception as e:
                self.logger.error(f"❌ Order update callback error: {e}")

    def _update_account_state(self, order: Dict) -> None:
        """Update balance and positions based on filled order."""
        side = order["side"]
        amount = order["amount"]
        price = order["price"]
        fee = order["fee"]["cost"]
        symbol = order["symbol"]

        # 1. Deduct Fee
        self._balance -= fee

        # 2. Update Position
        # Check if we have an existing position
        position = next((p for p in self._positions if p["symbol"] == symbol), None)

        if not position:
            # New Position
            if order.get("params", {}).get("reduceOnly"):
                self.logger.warning(f"⚠️ ReduceOnly order {order['id']} executed but no position found.")
                return

            new_pos = {
                "symbol": symbol,
                "side": "LONG" if side == "buy" else "SHORT",
                "amount": amount,
                "entry_price": price,
                "timestamp": self._current_timestamp,
            }
            self._positions.append(new_pos)
            # Deduct margin (simplified: 1x leverage)
            self._balance -= amount * price

        else:
            # Existing Position
            pos_side = position["side"]
            is_increase = (pos_side == "LONG" and side == "buy") or (pos_side == "SHORT" and side == "sell")

            if is_increase:
                # Increase position
                total_amount = position["amount"] + amount
                # Weighted average entry price
                total_cost = (position["amount"] * position["entry_price"]) + (amount * price)
                position["entry_price"] = total_cost / total_amount
                position["amount"] = total_amount
                # Deduct margin
                self._balance -= amount * price

            else:
                # Decrease/Close position
                close_amount = min(amount, position["amount"])
                remaining = position["amount"] - close_amount

                # Calculate PnL (Net of fees)
                # Gross PnL
                if pos_side == "LONG":
                    gross_pnl = (price - position["entry_price"]) * close_amount
                else:
                    gross_pnl = (position["entry_price"] - price) * close_amount

                # Calculate fees for closing trade
                # Note: fees are calculated on notional value (price * amount)
                closing_fee = close_amount * price * self.fee_rate

                # Calculate estimated opening fee (proportional to closed amount)
                # We assume entry was Taker (conservative) as most entries are Market
                opening_fee = close_amount * position["entry_price"] * self.fee_rate

                # Net PnL = Gross PnL - Closing Fee - Opening Fee
                # This ensures we capture the full round-trip cost
                pnl = gross_pnl - closing_fee - opening_fee

                # Return margin + PnL
                margin_released = close_amount * position["entry_price"]
                self._balance += margin_released + pnl

                # Store PnL in order for reporting
                order["realized_pnl"] = pnl

                if remaining < self.min_amount:
                    self._positions.remove(position)
                else:
                    position["amount"] = remaining

        # 3. Record Trade
        trade_record = {
            "id": f"tr_{self._order_seq}",
            "order": order["id"],
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "fee": fee,
            "timestamp": self._current_timestamp,
            "pnl": order.get("realized_pnl"),  # None for opening trades
            "gemini_trade_id": order.get("params", {}).get("gemini_trade_id"),
        }

        # Add entry details for closing trades
        if order.get("realized_pnl") is not None:
            trade_record["entry_price"] = position["entry_price"]
            trade_record["entry_time"] = position["timestamp"]
            trade_record["position_side"] = position["side"]

        self._trades.append(trade_record)

    def _cancel_siblings(self, filled_order: Dict) -> None:
        """
        Cancel sibling orders (OCO behavior).
        If a TP fills, cancel the SL, and vice versa.
        Uses registered OCO pairs from register_oco_pair().
        """
        filled_order_id = filled_order["id"]

        # Check if this order is part of an OCO pair
        sibling_id = self._oco_pairs.get(filled_order_id)
        if not sibling_id:
            # Fallback to old parent-based system
            parent_id = filled_order.get("params", {}).get("parent")
            if not parent_id:
                return

            symbol = filled_order["symbol"]
            for oid, order in self._orders.items():
                if (
                    order["status"] == "open"
                    and order["symbol"] == symbol
                    and order.get("params", {}).get("parent") == parent_id
                    and oid != filled_order_id
                ):
                    order["status"] = "canceled"
                    order["canceled_timestamp"] = self._current_timestamp
                    self.logger.info(f"🔄 Sibling order canceled (OCO/parent) | id={oid}")
            return

        # Cancel the sibling order using OCO pair registration
        sibling_order = self._orders.get(sibling_id)
        if sibling_order and sibling_order["status"] == "open":
            sibling_order["status"] = "canceled"
            sibling_order["canceled_timestamp"] = self._current_timestamp
            self.logger.info(f"🔄 OCO sibling canceled | Filled: {filled_order_id} -> Cancelled: {sibling_id}")

            # Notify callback about cancelled order too
            if self._order_update_callback:
                try:
                    normalized = self._normalize_order(sibling_order)
                    self._order_update_callback(normalized)
                except Exception as e:
                    self.logger.error(f"❌ Sibling cancel callback error: {e}")

        # Clean up OCO pair tracking
        if filled_order_id in self._oco_pairs:
            del self._oco_pairs[filled_order_id]
        if sibling_id in self._oco_pairs:
            del self._oco_pairs[sibling_id]

    # =========================================================
    # 💰 ACCOUNT DATA
    # =========================================================

    async def fetch_balance(self) -> Dict[str, Any]:
        """Return current simulated balance."""
        return {
            self.base_currency: {
                "free": self._balance,
                "used": 0.0,
                "total": self._balance,
            },
            "free": {self.base_currency: self._balance},
            "used": {self.base_currency: 0.0},
            "total": {self.base_currency: self._balance},
            "timestamp": self._current_timestamp,
        }

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Return open positions."""
        positions = []
        for p in self._positions:
            if symbols and p["symbol"] not in symbols:
                continue

            # Calculate unrealized PnL
            current_price = self._current_price
            if p["side"] == "LONG":
                upnl = (current_price - p["entry_price"]) * p["amount"]
            else:
                upnl = (p["entry_price"] - current_price) * p["amount"]

            positions.append(
                {
                    "symbol": p["symbol"],
                    "side": p["side"],
                    "contracts": p["amount"],
                    "entryPrice": p["entry_price"],
                    "unrealizedPnl": upnl,
                    "timestamp": p["timestamp"],
                }
            )
        return positions

    # =========================================================
    # 📝 ORDER EXECUTION
    # =========================================================

    async def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new order."""
        # Handle 'type' alias for 'order_type' (compatibility)
        if "type" in kwargs:
            order_type = kwargs["type"]

        # Validate amount
        amount = round(amount, self.amount_precision)
        if amount < self.min_amount:
            raise ValueError(f"Amount {amount} < min {self.min_amount}")

        self._order_seq += 1
        order_id = f"v_{self._current_timestamp}_{self._order_seq}"

        order = {
            "id": order_id,
            "order_id": order_id,  # For Croupier compatibility
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "type": order_type,
            "price": price,  # None for market
            "status": "open",
            "filled": 0.0,
            "remaining": amount,
            "cost": 0.0,
            "fee": {"cost": 0.0, "currency": self.base_currency},
            "timestamp": self._current_timestamp,
            "params": params or {},
            "stopPrice": (params or {}).get("stopPrice"),
        }

        self._orders[order_id] = order

        # If Market order (but NOT conditional market orders), execute immediately
        # Conditional orders like 'stop_market' and 'take_profit_market' should wait for trigger
        is_conditional = "stop" in order_type or "take_profit" in order_type

        if order_type == "market" and not is_conditional:
            # Use current price
            self._execute_order_fill(order, self._current_price)
        else:
            # Log creation of pending order
            stop_price = (params or {}).get("stopPrice")
            price_str = f"stop={stop_price:.2f}" if stop_price else (f"{price:.2f}" if price else "MKT")
            self.logger.info(f"📝 Order created | {side.upper()} {amount} @ {price_str} | id={order_id}")

        return order

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        orders = [o for o in self._orders.values() if o["status"] == "open"]
        if symbol:
            orders = [o for o in orders if o["symbol"] == symbol]
        return orders

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order["status"] == "open":
            order["status"] = "canceled"
            order["canceled_timestamp"] = self._current_timestamp
            self.logger.info(f"🛑 Order canceled | id={order_id}")

        return order

    async def fetch_order(self, order_id: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Fetch an order by ID."""
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return order

    # =========================================================
    # 🔧 UTILITY METHODS
    # =========================================================

    def normalize_symbol(self, symbol: str) -> str:
        return symbol

    def denormalize_symbol(self, exchange_symbol: str) -> str:
        return exchange_symbol

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data.
        """
        if not self._current_price:
            # If no price yet (start of backtest), return 0 or raise
            # But usually update_market_state is called before execution
            return {
                "symbol": symbol,
                "timestamp": self._current_timestamp,
                "datetime": str(self._current_timestamp),
                "high": 0.0,
                "low": 0.0,
                "bid": 0.0,
                "bidVolume": 0.0,
                "ask": 0.0,
                "askVolume": 0.0,
                "vwap": 0.0,
                "open": 0.0,
                "close": 0.0,
                "last": 0.0,
                "previousClose": 0.0,
                "change": 0.0,
                "percentage": 0.0,
                "average": 0.0,
                "baseVolume": 0.0,
                "quoteVolume": 0.0,
                "info": {},
            }

        return {
            "symbol": symbol,
            "timestamp": self._current_timestamp,
            "datetime": str(self._current_timestamp),
            "high": self._current_price,
            "low": self._current_price,
            "bid": self._current_price,
            "bidVolume": 1000.0,
            "ask": self._current_price,
            "askVolume": 1000.0,
            "vwap": self._current_price,
            "open": self._current_price,
            "close": self._current_price,
            "last": self._current_price,
            "previousClose": self._current_price,
            "change": 0.0,
            "percentage": 0.0,
            "average": self._current_price,
            "baseVolume": 1000.0,
            "quoteVolume": 1000.0 * self._current_price,
            "info": {},
        }

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        # VirtualExchange doesn't store history, it just consumes it.
        # This method is rarely used by Croupier (it uses DataSource).
        return []

    def _normalize_order(self, order: Dict) -> Dict:
        """
        Normalize order to standard format (matching BinanceNativeConnector).

        This ensures VirtualExchange returns the same format as real exchanges.
        """
        return {
            "id": str(order["id"]),
            "order_id": str(order.get("order_id", order["id"])),  # Alias for Croupier
            "symbol": order["symbol"],
            "status": order["status"],
            "price": float(order.get("price", 0) or 0),
            "amount": float(order["amount"]),
            "filled": float(order.get("filled", 0) or 0),
            "type": order["type"],
            "side": order["side"],
            "timestamp": order.get("timestamp", self._current_timestamp),
            "info": order,  # Raw order for reference
        }

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a trade to standard format and detect closes.
        Matching BinanceNativeConnector.normalize_trade().
        """
        realized_pnl = float(raw_trade.get("pnl", 0) or 0)

        return {
            **raw_trade,
            "is_close": realized_pnl != 0,
            "realized_pnl": realized_pnl,
            "close_reason": "TP" if realized_pnl > 0 else ("SL" if realized_pnl < 0 else None),
        }
