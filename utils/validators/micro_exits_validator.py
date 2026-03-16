#!/usr/bin/env python3
"""
Validator for Phase 3: Order Flow Micro-Exits
Verifies that the `ExitManager.on_microstructure` correctly identifies:
1. Liquidity Pulls (Spoofing)
2. Delta Inversion Bursts (against the position)
And correctly triggers `close_position`.
"""
import asyncio
import logging
import os
import sys

# Ensure Casino-V3 is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.events import EventType, MicrostructureEvent
from croupier.components.exit_manager import ExitManager


class MockPositionTracker:
    def __init__(self, positions):
        self.positions = positions

    def get_positions_by_symbol(self, symbol):
        return [p for p in self.positions if p.symbol == symbol]


class MockPosition:
    def __init__(self, symbol, side, status="OPEN", id="trc_mock", timestamp=0.0):
        self.symbol = symbol
        self.side = side
        self.status = status
        self.trade_id = id
        self.timestamp = timestamp


class MockErrorHandler:
    shutdown_mode = False


class MockCroupier:
    def __init__(self, positions):
        self.position_tracker = MockPositionTracker(positions)
        self.error_handler = MockErrorHandler()
        self.closed_positions = []
        self.exit_reasons = []

    async def close_position(self, trade_id, exit_reason=""):
        self.closed_positions.append(trade_id)
        self.exit_reasons.append(exit_reason)


def ok(msg):
    print(f"✅ {msg}")


def fail(msg):
    print(f"❌ {msg}")
    sys.exit(1)


async def run_validator():
    print("=" * 60)
    print(" STRATEGY 2.0 VALIDATOR: MICRO-EXITS (ORDER FLOW)")
    print("=" * 60)

    # Setup Scenarios
    pos_long = MockPosition("BTCUSDT", "LONG", id="long_1")
    pos_short = MockPosition("BTCUSDT", "SHORT", id="short_1")

    mock_croupier = MockCroupier([pos_long, pos_short])
    exit_manager = ExitManager(mock_croupier)

    # Disable logging to keep output clean
    logging.getLogger("ExitManager").setLevel(logging.CRITICAL)

    # ---------------------------------------------------------
    # Scenario 1: Liquidity Pull on LONG (Bid Wall Collapse)
    # Long positions need Skewness > 0. If it drops to < 0.20, it's a pull.
    # ---------------------------------------------------------
    event_pull_long = MicrostructureEvent(
        type=EventType.MICROSTRUCTURE,
        timestamp=10.0,
        symbol="BTCUSDT",
        cvd=10.0,  # Normal CVD
        skewness=0.14,  # Danger! Bid wall pulled (< 0.15).
        price=50000.0,
    )

    await exit_manager.on_microstructure(event_pull_long)
    await asyncio.sleep(0.1)  # Let the CreateTask close_position run

    if "long_1" not in mock_croupier.closed_positions:
        fail("Logic Error: Failed to trigger Micro-Exit for LONG on Bid Wall Collapse (Skewness < 0.20)")
    else:
        reason = mock_croupier.exit_reasons[mock_croupier.closed_positions.index("long_1")]
        if reason != "MICRO_LIQUIDITY_PULL_BID_WALL_COLLAPSE":
            fail(f"Logic Error: Wrong exit reason {reason}")
        ok("Liquidity Pull (LONG) detected securely")

    # Clear state
    mock_croupier.closed_positions.clear()
    mock_croupier.exit_reasons.clear()

    # ---------------------------------------------------------
    # Scenario 2: Liquidity Pull on SHORT (Ask Wall Collapse)
    # Short positions need Ask pressure (Skewness < 1.0). If it > 0.80, danger.
    # ---------------------------------------------------------
    event_pull_short = MicrostructureEvent(
        type=EventType.MICROSTRUCTURE,
        timestamp=10.0,
        symbol="BTCUSDT",
        cvd=-10.0,
        skewness=0.86,  # Danger! Ask wall pulled (> 0.85).
        price=50000.0,
    )

    await exit_manager.on_microstructure(event_pull_short)
    await asyncio.sleep(0.1)

    if "short_1" not in mock_croupier.closed_positions:
        fail("Logic Error: Failed to trigger Micro-Exit for SHORT on Ask Wall Collapse (Skewness > 0.80)")
    else:
        ok("Liquidity Pull (SHORT) detected securely")

    mock_croupier.closed_positions.clear()
    mock_croupier.exit_reasons.clear()

    # ---------------------------------------------------------
    # Scenario 3: Delta Inversion Burst (Against LONG)
    # Notional CVD < -$50k
    # ---------------------------------------------------------
    event_burst_long = MicrostructureEvent(
        type=EventType.MICROSTRUCTURE,
        timestamp=10.0,
        symbol="BTCUSDT",
        cvd=-1.5,
        skewness=0.5,
        price=50000.0,
        z_score=-4.0,  # Danger! Negative burst (< -3.5)
    )

    await exit_manager.on_microstructure(event_burst_long)
    await asyncio.sleep(0.1)

    if "long_1" not in mock_croupier.closed_positions:
        fail("Logic Error: Failed to trigger Micro-Exit for LONG on Negative Z-Score Burst")
    else:
        reason = mock_croupier.exit_reasons[mock_croupier.closed_positions.index("long_1")]
        if not reason.startswith("MICRO_Z_DELTA_BURST_SHORT"):
            fail(f"Logic Error: Wrong exit reason {reason}")
        ok("Delta Inversion Burst (against LONG) detected securely")

    mock_croupier.closed_positions.clear()
    mock_croupier.exit_reasons.clear()

    # ---------------------------------------------------------
    # Scenario 4: Safe Order Flow (No Exit)
    # ---------------------------------------------------------
    event_safe = MicrostructureEvent(
        type=EventType.MICROSTRUCTURE,
        timestamp=10.0,
        symbol="BTCUSDT",
        cvd=0.5,
        skewness=0.5,
        price=50000.0,
    )

    await exit_manager.on_microstructure(event_safe)
    await asyncio.sleep(0.1)

    if len(mock_croupier.closed_positions) > 0:
        fail("Logic Error: Triggered Micro-Exit on Safe Order Flow!")
    else:
        ok("Safe Order Flow (No False Positives) verified")

    print("\n✅ STRATEGY 2.0 VALIDATOR: MICRO-EXITS PASSED\n")


if __name__ == "__main__":
    asyncio.run(run_validator())
