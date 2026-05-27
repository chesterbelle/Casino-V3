"""
Decision Pipeline Validator - TraceBullet Data Integrity Fuzzer
-------------------------------------------------------------
Project TraceBullet enforces structural math and invariant checking
across the entire Casino-V3 execution pipeline.

It generates synthetic `TradeProposal`s with unique `trace_id`s,
throws them at the Execution Engine with random simulated latencies,
and intercepts the final outbound Exchange JSON payloads.

It then compares [Border A] (Strategy Intent) vs. [Border D] (Exchange Output)
to guarantee no Race Conditions or Math Corruptions mutated the data.

Usage:
    python -m utils.validators.decision_pipeline_validator
"""

import asyncio
import logging
import os
import random
import sys
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.events import EventType
from core.execution import OrderManager
from core.portfolio.position_tracker import PositionTracker
from croupier.components.oco_manager import OCOManager
from croupier.croupier import Croupier
from decision.engine.proposal import TradeProposal
from players.adaptive import AdaptivePlayer


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(message)s",
        handlers=[logging.StreamHandler()],
    )


logger = logging.getLogger("TraceBullet")

# =====================================================================
# THE SHADOW LEDGER (Global State Tracker)
# =====================================================================
# trace_id -> {"proposal": TradeProposal, "border_d_tp": payload, "border_d_sl": payload, "fill_price": 0.0}
SHADOW_LEDGER = {}

# =====================================================================
# MOCK INFRASTRUCTURE (The Sandbox)
# =====================================================================


class MockEventEngine:
    def __init__(self):
        self.handlers = {}

    def subscribe(self, event_type, handler):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)

    async def dispatch(self, proposal: TradeProposal):
        # [BORDER A] Record Strategy Output
        SHADOW_LEDGER[proposal.trace_id] = {
            "proposal": proposal,
            "border_d_tp": None,
            "border_d_sl": None,
            "fill_price": 0.0,
        }
        for handler in self.handlers.get(EventType.TRADE_PROPOSAL, []):
            await handler(proposal)


class MockOrderExecutor:
    def __init__(self, adapter):
        self.adapter = adapter

    async def execute_market_order(self, symbol, side, amount, **kwargs):
        await asyncio.sleep(random.uniform(0.01, 0.05))
        order_id = f"MOCK_{uuid.uuid4().hex[:8]}"
        return {
            "order_id": order_id,
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "type": "MARKET",
            "status": "closed",
        }

    async def execute_stop_order(
        self,
        symbol,
        side,
        amount,
        stop_price=None,
        price=None,
        client_order_id=None,
        order_type=None,
        params=None,
        **kwargs,
    ):
        if params is None:
            params = {"reduceOnly": "true", "client_order_id": client_order_id}
        elif client_order_id:
            params["client_order_id"] = client_order_id
        if stop_price and "stopPrice" not in params:
            params["stopPrice"] = stop_price
        return await self.adapter.create_order(
            symbol=symbol,
            order_type=order_type or ("STOP_MARKET" if stop_price else "LIMIT"),
            side=side,
            amount=amount,
            price=price or stop_price,
            params=params,
        )


class DummyConnector:
    def __init__(self):
        self.__class__.__name__ = "MockNativeConnector"


class MockExchangeAdapter:
    def __init__(self):
        self.connector = DummyConnector()

    def price_to_precision(self, symbol, price):
        return f"{price:.4f}"

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.2f}"

    def normalize_symbol(self, symbol):
        return symbol.replace("/", "").replace(":", "")

    async def get_current_price(self, symbol):
        return 100.0

    def get_cached_price(self, symbol):
        return 100.0

    def get_min_notional(self, symbol):
        return 10.0

    def is_cache_stale(self, *args, **kwargs):
        return False

    async def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        await asyncio.sleep(random.uniform(0.01, 0.05))
        order_id = f"MOCK_BRACKET_{uuid.uuid4().hex[:8]}"
        payload = {
            "id": order_id,
            "order_id": order_id,
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "params": params or {},
        }
        # [BORDER D] Intercept Exchange Payload
        trace_id = getattr(self, "symbol_trace_map", {}).get(symbol, "UNKNOWN")
        if trace_id in SHADOW_LEDGER:
            if "TAKE_PROFIT" in str(order_type).upper() or "LIMIT" in str(order_type).upper():
                SHADOW_LEDGER[trace_id]["border_d_tp"] = payload
            else:
                SHADOW_LEDGER[trace_id]["border_d_sl"] = payload
        else:
            logger.warning(f"⚠️ [BORDER D] Orphaned payload with no matching trace! Symbol: {symbol}")
        return payload

    async def fetch_order(self, id, symbol):
        return {"id": id, "status": "closed", "symbol": symbol, "info": {}}

    async def cancel_order(self, id, symbol):
        return {"id": id, "status": "canceled"}


class MockCroupier:
    def __init__(self, engine, adapter):
        self.exchange_adapter = adapter
        self.tracker = PositionTracker()
        self.order_executor = MockOrderExecutor(adapter)
        self.oco_manager = OCOManager(
            order_executor=self.order_executor,
            position_tracker=self.tracker,
            exchange_adapter=adapter,
        )

        async def mock_execute_main_order(order, client_order_id):
            fill_price = order.get("estimated_price", 100.0) * random.uniform(0.9995, 1.0005)
            for tid, data in SHADOW_LEDGER.items():
                intent = data.get("proposal")
                if intent and intent.symbol == order.get("symbol") and data.get("fill_price") == 0.0:
                    SHADOW_LEDGER[tid]["fill_price"] = fill_price
                    break
            return {
                "id": f"MOCK_MAIN_{uuid.uuid4().hex[:8]}",
                "price": fill_price,
                "amount": order["amount"],
                "status": "filled",
            }

        self.oco_manager._execute_main_order = mock_execute_main_order

        async def mock_wait_for_fill(order_id, symbol, timeout=10.0, future=None):
            if future and not future.done():
                future.set_result({"price": 100.0, "fee": {"cost": 0.1}})
            return {"price": 100.0, "fee": {"cost": 0.1}}

        self.oco_manager._wait_for_fill = mock_wait_for_fill

        async def mock_monitor_bracket_watchdog(*args, **kwargs):
            pass

        self.oco_manager.active_oco_operations = type("MockDict", (dict,), {"__contains__": lambda self, key: False})()

    def get_equity(self):
        return 1000.0

    def get_active_positions(self):
        return []

    async def execute_order(self, order_payload):
        return await self.oco_manager.create_bracketed_order(order_payload, wait_for_fill=True)


# =====================================================================
# THE VALIDATOR RUNNER
# =====================================================================


class TraceBulletValidator:
    def __init__(self):
        self.engine = MockEventEngine()
        self.adapter = MockExchangeAdapter()
        self.croupier = MockCroupier(self.engine, self.adapter)

        self.adapter.symbol_trace_map = {}

        # Initialize AdaptivePlayer in V8.5 mode (no fixed_pct/use_kelly)
        self.player = AdaptivePlayer(
            engine=self.engine,
            croupier=self.croupier,
        )

        # Subscribe MockEventEngine to TRADE_PROPOSAL
        self.engine.subscribe(EventType.TRADE_PROPOSAL, self.player.on_trade_proposal)

        # Hook Croupier execution to register trace_id -> symbol for Border D interception
        self._symbol_trace_map = self.adapter.symbol_trace_map
        self._original_execute = self.croupier.execute_order

        async def hooked_execute_order(payload):
            trace_id = payload.get("trace_id")
            symbol = payload.get("symbol")
            if trace_id and symbol:
                self._symbol_trace_map[symbol] = trace_id
            return await self._original_execute(payload)

        self.croupier.execute_order = hooked_execute_order

        # Bypass ErrorHandler circuit breakers
        async def bypass_breaker(operation_id, func, *args, **kwargs):
            kwargs.pop("retry_config", None)
            kwargs.pop("context", None)
            kwargs.pop("timeout", None)
            return await func(*args, **kwargs)

        self.croupier.oco_manager.error_handler.execute_with_breaker = bypass_breaker

    async def run_chaos_fuzzer(self, iterations: int = 25) -> bool:
        """
        Creates a storm of TradeProposals to test pipeline integrity.
        """
        logger.info(
            f"\n{'='*80}\n" f"🌪️ TRACEBULLET: CHAOS FUZZER (Storm of {iterations} concurrent proposals)\n" f"{'='*80}"
        )

        tasks = []
        for i in range(iterations):
            trace_id = f"TRX_{uuid.uuid4().hex[:6].upper()}_{i}"
            side = random.choice(["LONG", "SHORT"])
            symbol = random.choice(["LTCUSDT", "ETHUSDT"])

            base_price = 100.0 + (i * 0.02)
            if side == "LONG":
                tp_price = base_price * 1.008
                sl_price = base_price * 0.992
            else:
                tp_price = base_price * 0.992
                sl_price = base_price * 1.008

            grade = random.choice(["A", "B"])

            proposal = TradeProposal(
                symbol=symbol,
                side=side,
                entry_price=base_price,
                tp_price=tp_price,
                sl_price=sl_price,
                grade=grade,
                narrative=f"chaos_{i}_{grade}",
                trace_id=trace_id,
                timestamp=time.time(),
            )
            tasks.append(self.engine.dispatch(proposal))

        for t in tasks:
            await t
            await asyncio.sleep(0.05)

        logger.info("⏳ Waiting for Execution Pipelines to flush into Border D...")
        await asyncio.sleep(2.0)

        return self._verify_invariants(iterations)

    def _verify_invariants(self, expected_count: int) -> bool:
        logger.info(f"\n{'='*80}\n" f"🛡️ VALIDATING INVARIANTS ON {len(SHADOW_LEDGER)} TRACES\n" f"{'='*80}")

        if len(SHADOW_LEDGER) != expected_count:
            logger.error(
                f"❌ [RACE CONDITION] Event Loss. " f"Expected {expected_count} traces, got {len(SHADOW_LEDGER)}."
            )
            return False

        failures = 0

        for trace_id, data in SHADOW_LEDGER.items():
            proposal: TradeProposal = data.get("proposal")
            border_d_tp = data.get("border_d_tp")
            border_d_sl = data.get("border_d_sl")
            fill_price = data.get("fill_price", 0.0)

            if not proposal or not border_d_tp or not border_d_sl:
                logger.error(
                    f"❌ [DATA LOSS] Trace {trace_id} did not complete the pipeline " f"(Missing proposal, TP, or SL)."
                )
                failures += 1
                continue

            sent_tp = float(border_d_tp.get("price", 0))
            sent_sl = float(border_d_sl.get("price", 0) or border_d_sl.get("params", {}).get("stopPrice", 0))

            if proposal.side == "LONG":
                if sent_tp <= fill_price:
                    logger.error(
                        f"❌ [FATAL MATH INVERSION] Trace {trace_id} (LONG). " f"TP {sent_tp} is <= Fill {fill_price}."
                    )
                    failures += 1
                if sent_sl >= fill_price:
                    logger.error(
                        f"❌ [FATAL MATH INVERSION] Trace {trace_id} (LONG). " f"SL {sent_sl} is >= Fill {fill_price}."
                    )
                    failures += 1
                if border_d_tp.get("side", "").upper() != "SELL" or border_d_sl.get("side", "").upper() != "SELL":
                    logger.error(
                        f"❌ [TOPOLOGICAL INVERSION] Trace {trace_id} (LONG). "
                        f"Sides: TP {border_d_tp.get('side')} / SL {border_d_sl.get('side')}."
                    )
                    failures += 1

            elif proposal.side == "SHORT":
                if sent_tp >= fill_price:
                    logger.error(
                        f"❌ [FATAL MATH INVERSION] Trace {trace_id} (SHORT). " f"TP {sent_tp} is >= Fill {fill_price}."
                    )
                    failures += 1
                if sent_sl <= fill_price:
                    logger.error(
                        f"❌ [FATAL MATH INVERSION] Trace {trace_id} (SHORT). " f"SL {sent_sl} is <= Fill {fill_price}."
                    )
                    failures += 1
                if border_d_tp.get("side", "").upper() != "BUY" or border_d_sl.get("side", "").upper() != "BUY":
                    logger.error(
                        f"❌ [TOPOLOGICAL INVERSION] Trace {trace_id} (SHORT). "
                        f"Sides: TP {border_d_tp.get('side')} / SL {border_d_sl.get('side')}."
                    )
                    failures += 1

            # closePosition orders (notional < min) have amount=0 — skip sizing check
            tp_uses_close = border_d_tp.get("params", {}).get("closePosition", False)
            sl_uses_close = border_d_sl.get("params", {}).get("closePosition", False)
            if not (tp_uses_close or sl_uses_close):
                sent_tp_amt = float(border_d_tp.get("amount", 0))
                sent_sl_amt = float(border_d_sl.get("amount", 0))
                if sent_tp_amt != sent_sl_amt or sent_tp_amt <= 0:
                    logger.error(
                        f"❌ [SIZING CORRUPTION] Trace {trace_id}. "
                        f"TP Amt {sent_tp_amt} != SL Amt {sent_sl_amt} or <= 0"
                    )
                    failures += 1

        if failures > 0:
            logger.error(f"❌ VALIDATION FAILED. {failures} Invariant Violations found.")
            return False

        logger.info(f"✅ TRACEBULLET PASSED! 0 Data Mutations " f"across {expected_count} concurrent operations.")
        return True


async def main():
    setup_logging()
    validator = TraceBulletValidator()
    passed = await validator.run_chaos_fuzzer(iterations=25)

    if passed:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
