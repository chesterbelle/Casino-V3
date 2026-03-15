"""
DataFeed Validator - Flow Integrity Verification
-------------------------------------------------
This validator verifies that each component in the pipeline receives and emits
data correctly, identifying points of data loss.

Verifies 8 critical points:
1. BacktestFeed._emit_tick() - Emits TickEvent with correct side?
2. CandleMaker.on_tick() - Accumulates profile?
3. CandleMaker._emit_candle() - Calculates POC?
4. ContextRegistry.on_tick() - Accumulates trades?
5. ContextRegistry.get_structural() - Returns POC > 0?
6. SensorManager.on_candle() - Passes profile?
7. SessionValueArea.calculate() - Calculates levels?
8. SetupEngine._enrich_metadata() - Receives POC?

Usage:
    python -m utils.validators.datafeed_validator --data data/raw/LTCUSDT_trades_2026_01.csv --limit 10000
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.events import EventType


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/datafeed_validator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
        handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
    )

    # Enable DEBUG for key components
    logging.getLogger("CandleMaker").setLevel(logging.DEBUG)
    logging.getLogger("SensorManager").setLevel(logging.DEBUG)
    logging.getLogger("SessionValueArea").setLevel(logging.DEBUG)


logger = logging.getLogger("DataFeedValidator")


class DataFeedValidator:
    """
    Validates that each function in the pipeline works correctly.

    Tests 8 critical points in the data flow.
    """

    def __init__(self, output_dir: str = "data/validation"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    async def verify_flow_integrity(self, data_path: str, symbol: str, limit: int = 10000):
        """
        Verify that each function in the pipeline works correctly.

        Tests 8 critical points:
        1. BacktestFeed._emit_tick() - Emits TickEvent with correct side?
        2. CandleMaker.on_tick() - Accumulates profile?
        3. CandleMaker._emit_candle() - Calculates POC?
        4. ContextRegistry.on_tick() - Accumulates trades?
        5. ContextRegistry.get_structural() - Returns POC > 0?
        6. SensorManager.on_candle() - Passes profile?
        7. SessionValueArea.calculate() - Calculates levels?
        8. SetupEngine._enrich_metadata() - Receives POC?
        """
        from core.backtest_feed import BacktestFeed
        from core.candle_maker import CandleMaker
        from core.context_registry import ContextRegistry
        from core.engine import Engine
        from core.sensor_manager import SensorManager
        from decision.setup_engine import SetupEngineV4
        from sensors.footprint.session import SessionValueArea

        logger.info("=" * 70)
        logger.info(" FLOW INTEGRITY VERIFICATION")
        logger.info("=" * 70)

        results = {}

        # =====================================================================
        # TEST 1: BacktestFeed._emit_tick()
        # =====================================================================
        logger.info("\n📋 TEST 1: BacktestFeed._emit_tick()")

        engine1 = Engine()
        tick_emitted = None

        async def capture_tick(event):
            nonlocal tick_emitted
            tick_emitted = event

        engine1.subscribe(EventType.TICK, capture_tick)

        feed = BacktestFeed(engine=engine1, data_path=data_path, symbol=symbol, limit=1)
        await feed.run()

        if tick_emitted:
            side = getattr(tick_emitted, "side", None)
            price = getattr(tick_emitted, "price", 0)
            volume = getattr(tick_emitted, "volume", 0)
            timestamp = getattr(tick_emitted, "timestamp", 0)

            if side in ["BID", "ASK"]:
                results["BacktestFeed._emit_tick"] = {
                    "status": "PASS",
                    "output": f"TickEvent(side={side}, price={price}, volume={volume})",
                    "details": {"side": side, "price": price, "volume": volume, "timestamp": timestamp},
                }
                logger.info(f"  ✅ PASS: TickEvent emitted with side={side}")
            else:
                results["BacktestFeed._emit_tick"] = {
                    "status": "FAIL",
                    "output": f"Invalid side: {side}",
                    "reason": "Side must be BID or ASK",
                }
                logger.error(f"  ❌ FAIL: Invalid side={side}")
        else:
            results["BacktestFeed._emit_tick"] = {
                "status": "FAIL",
                "output": "No tick emitted",
                "reason": "BacktestFeed did not emit TickEvent",
            }
            logger.error("  ❌ FAIL: No tick emitted")

        # =====================================================================
        # TEST 2: CandleMaker.on_tick()
        # =====================================================================
        logger.info("\n📋 TEST 2: CandleMaker.on_tick()")

        engine2 = Engine()
        candle_maker = CandleMaker(engine2)

        # Create a mock tick
        from core.events import TickEvent

        mock_tick = TickEvent(
            type=EventType.TICK, timestamp=time.time(), symbol=symbol, price=100.0, volume=10.0, side="BID"
        )

        await candle_maker.on_tick(mock_tick)

        # Check internal state after
        current_candle = candle_maker.current_candles.get(symbol, {})
        profile_after = current_candle.get("profile", {})

        if profile_after and 100.0 in profile_after:
            bid_vol = profile_after[100.0].get("bid", 0)
            results["CandleMaker.on_tick"] = {
                "status": "PASS",
                "output": f"Profile accumulated: price=100.0, bid={bid_vol}",
                "details": {"profile_levels": len(profile_after), "bid_vol": bid_vol},
            }
            logger.info(f"  ✅ PASS: Profile accumulated with bid={bid_vol}")
        else:
            results["CandleMaker.on_tick"] = {
                "status": "FAIL",
                "output": f"Profile not accumulated",
                "reason": "Tick did not update profile",
            }
            logger.error("  ❌ FAIL: Profile not accumulated")

        # =====================================================================
        # TEST 3: CandleMaker._emit_candle()
        # =====================================================================
        logger.info("\n📋 TEST 3: CandleMaker._emit_candle()")

        engine3 = Engine()
        candle_maker3 = CandleMaker(engine3)

        # Create candle data with profile
        candle_data = {
            "timestamp": time.time(),
            "symbol": symbol,
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1000.0,
            "profile": {
                100.0: {"bid": 100.0, "ask": 50.0},
                101.0: {"bid": 200.0, "ask": 100.0},
                102.0: {"bid": 150.0, "ask": 75.0},
            },
            "delta": 0.0,
        }

        candle_event = None

        async def capture_candle(event):
            nonlocal candle_event
            candle_event = event

        engine3.subscribe(EventType.CANDLE, capture_candle)
        await candle_maker3._emit_candle(candle_data)

        if candle_event:
            poc = getattr(candle_event, "poc", 0.0)
            vah = getattr(candle_event, "vah", 0.0)
            val = getattr(candle_event, "val", 0.0)

            if poc > 0:
                results["CandleMaker._emit_candle"] = {
                    "status": "PASS",
                    "output": f"POC={poc:.2f}, VAH={vah:.2f}, VAL={val:.2f}",
                    "details": {"poc": poc, "vah": vah, "val": val},
                }
                logger.info(f"  ✅ PASS: POC calculated = {poc:.2f}")
            else:
                results["CandleMaker._emit_candle"] = {
                    "status": "FAIL",
                    "output": "POC=0.0",
                    "reason": "calculate_footprint_stats_worker returned 0.0",
                }
                logger.error("  ❌ FAIL: POC = 0.0")
        else:
            results["CandleMaker._emit_candle"] = {
                "status": "FAIL",
                "output": "No candle emitted",
                "reason": "_emit_candle did not dispatch event",
            }
            logger.error("  ❌ FAIL: No candle emitted")

        # =====================================================================
        # TEST 4: ContextRegistry.on_tick()
        # =====================================================================
        logger.info("\n📋 TEST 4: ContextRegistry.on_tick()")

        context_registry = ContextRegistry(tick_size=0.01)

        # Add some trades
        context_registry.on_tick(symbol, 100.0, 10.0, "buy", time.time())
        context_registry.on_tick(symbol, 101.0, 20.0, "buy", time.time())
        context_registry.on_tick(symbol, 102.0, 15.0, "sell", time.time())

        profile = context_registry.profiles.get(symbol)
        if profile and profile.total_volume > 0:
            results["ContextRegistry.on_tick"] = {
                "status": "PASS",
                "output": f"Total volume accumulated: {profile.total_volume}",
                "details": {"total_volume": profile.total_volume, "levels": len(profile.profile)},
            }
            logger.info(f"  ✅ PASS: Volume accumulated = {profile.total_volume}")
        else:
            results["ContextRegistry.on_tick"] = {
                "status": "FAIL",
                "output": "No trades accumulated",
                "reason": "MarketProfile not receiving trades",
            }
            logger.error("  ❌ FAIL: No trades accumulated")

        # =====================================================================
        # TEST 5: ContextRegistry.get_structural()
        # =====================================================================
        logger.info("\n📋 TEST 5: ContextRegistry.get_structural()")

        poc, vah, val = context_registry.get_structural(symbol)

        if poc > 0:
            results["ContextRegistry.get_structural"] = {
                "status": "PASS",
                "output": f"POC={poc:.2f}, VAH={vah:.2f}, VAL={val:.2f}",
                "details": {"poc": poc, "vah": vah, "val": val},
            }
            logger.info(f"  ✅ PASS: POC={poc:.2f}")
        else:
            results["ContextRegistry.get_structural"] = {
                "status": "FAIL",
                "output": "POC=0.0",
                "reason": "MarketProfile.calculate_value_area() returned 0.0",
            }
            logger.error("  ❌ FAIL: POC=0.0")

        # =====================================================================
        # TEST 6: SensorManager.on_candle()
        # =====================================================================
        logger.info("\n📋 TEST 6: SensorManager.on_candle()")

        engine6 = Engine()
        sensor_manager = SensorManager(engine6)

        # Create a mock candle event
        from core.events import FootprintCandleEvent

        mock_candle = FootprintCandleEvent(
            type=EventType.CANDLE,
            timestamp=time.time(),
            symbol=symbol,
            timeframe="1m",
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
            profile={100.0: {"bid": 100.0, "ask": 50.0}},
            delta=50.0,
            atr=2.0,
            poc=101.0,
            vah=102.0,
            val=100.0,
        )

        await sensor_manager.on_candle(mock_candle)

        # Check if aggregator has the candle
        aggregator = sensor_manager.aggregators.get(symbol)
        if aggregator and aggregator.history.get("1m"):
            last_candle = aggregator.history["1m"][-1]
            profile_passed = last_candle.get("profile")
            poc_passed = last_candle.get("poc", 0)

            if profile_passed and poc_passed > 0:
                results["SensorManager.on_candle"] = {
                    "status": "PASS",
                    "output": f"Profile passed, POC={poc_passed}",
                    "details": {"profile_levels": len(profile_passed), "poc": poc_passed},
                }
                logger.info(f"  ✅ PASS: Profile and POC passed to aggregator")
            else:
                results["SensorManager.on_candle"] = {
                    "status": "FAIL",
                    "output": f"Profile={profile_passed}, POC={poc_passed}",
                    "reason": "Profile or POC not passed correctly",
                }
                logger.error("  ❌ FAIL: Profile or POC not passed")
        else:
            results["SensorManager.on_candle"] = {
                "status": "FAIL",
                "output": "No aggregator or history",
                "reason": "SensorManager did not process candle",
            }
            logger.error("  ❌ FAIL: No aggregator or history")

        # =====================================================================
        # TEST 7: SessionValueArea.calculate()
        # =====================================================================
        logger.info("\n📋 TEST 7: SessionValueArea.calculate()")

        session_sensor = SessionValueArea(tick_size=0.01)

        # Create context with profile
        context = {
            "1m": {
                "timestamp": time.time(),
                "symbol": symbol,
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 102.0,
                "volume": 1000.0,
                "profile": {
                    100.0: {"bid": 100.0, "ask": 50.0},
                    101.0: {"bid": 200.0, "ask": 100.0},
                    102.0: {"bid": 150.0, "ask": 75.0},
                },
                "delta": 50.0,
            }
        }

        result = session_sensor.calculate(context)

        if result and result.get("metadata"):
            poc = result["metadata"].get("poc", 0)
            vah = result["metadata"].get("vah", 0)
            val = result["metadata"].get("val", 0)

            if poc > 0:
                results["SessionValueArea.calculate"] = {
                    "status": "PASS",
                    "output": f"POC={poc:.2f}, VAH={vah:.2f}, VAL={val:.2f}",
                    "details": {"poc": poc, "vah": vah, "val": val},
                }
                logger.info(f"  ✅ PASS: POC={poc:.2f}")
            else:
                results["SessionValueArea.calculate"] = {
                    "status": "FAIL",
                    "output": "POC=0.0",
                    "reason": "SessionValueArea did not calculate POC from profile",
                }
                logger.error("  ❌ FAIL: POC=0.0")
        else:
            results["SessionValueArea.calculate"] = {
                "status": "FAIL",
                "output": "No result or metadata",
                "reason": "calculate() returned None or no metadata",
            }
            logger.error("  ❌ FAIL: No result or metadata")

        # =====================================================================
        # TEST 8: SetupEngine._enrich_metadata()
        # =====================================================================
        logger.info("\n📋 TEST 8: SetupEngine._enrich_metadata()")

        engine8 = Engine()
        context_registry8 = ContextRegistry(tick_size=0.01)

        # Add trades to ContextRegistry first
        context_registry8.on_tick(symbol, 100.0, 100.0, "buy", time.time())
        context_registry8.on_tick(symbol, 101.0, 200.0, "buy", time.time())
        context_registry8.on_tick(symbol, 102.0, 150.0, "sell", time.time())

        setup_engine = SetupEngineV4(engine8, context_registry=context_registry8)

        metadata = {"trigger": "test"}
        enriched = setup_engine._enrich_metadata(metadata, symbol)

        poc = enriched.get("poc", 0)
        vah = enriched.get("vah", 0)
        val = enriched.get("val", 0)

        if poc > 0:
            results["SetupEngine._enrich_metadata"] = {
                "status": "PASS",
                "output": f"POC={poc:.2f}, VAH={vah:.2f}, VAL={val:.2f}",
                "details": {"poc": poc, "vah": vah, "val": val},
            }
            logger.info(f"  ✅ PASS: POC={poc:.2f}")
        else:
            results["SetupEngine._enrich_metadata"] = {
                "status": "FAIL",
                "output": "POC=0.0",
                "reason": "ContextRegistry.get_structural() returned 0.0 or context_registry is None",
            }
            logger.error("  ❌ FAIL: POC=0.0")

        # =====================================================================
        # SUMMARY
        # =====================================================================
        logger.info("\n" + "=" * 70)
        logger.info(" VERIFICATION SUMMARY")
        logger.info("=" * 70)

        passed = sum(1 for r in results.values() if r["status"] == "PASS")
        failed = sum(1 for r in results.values() if r["status"] == "FAIL")

        logger.info(f"\n✅ Passed: {passed}/8")
        logger.info(f"❌ Failed: {failed}/8")

        if failed > 0:
            logger.info("\n📋 FAILED TESTS:")
            for name, result in results.items():
                if result["status"] == "FAIL":
                    logger.info(f"  - {name}: {result['reason']}")

        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "data_path": data_path,
            "symbol": symbol,
            "limit": limit,
            "results": results,
            "summary": {"passed": passed, "failed": failed, "total": 8},
        }

        report_path = os.path.join(self.output_dir, "flow_integrity_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"\n📁 Report saved to {report_path}")

        return results


# =====================================================================
# CLI
# =====================================================================


def main():
    parser = argparse.ArgumentParser(description="DataFeed Validator - Verify Flow Integrity")
    parser.add_argument("--symbol", default="LTC/USDT:USDT", help="Symbol to validate")
    parser.add_argument("--data", default="data/raw/LTCUSDT_trades_2026_01.csv", help="Data file for backtest")
    parser.add_argument("--limit", type=int, default=10000, help="Tick limit for backtest")
    parser.add_argument("--output", default="data/validation", help="Output directory")

    args = parser.parse_args()

    setup_logging()
    validator = DataFeedValidator(output_dir=args.output)

    results = asyncio.run(validator.verify_flow_integrity(args.data, args.symbol, args.limit))
    failed = sum(1 for r in results.values() if r["status"] == "FAIL")
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
