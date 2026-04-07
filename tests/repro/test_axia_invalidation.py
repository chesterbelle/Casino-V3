import logging
from dataclasses import dataclass
from typing import Optional


# Mocking parts of the system
@dataclass
class TickEvent:
    symbol: str
    price: float
    timestamp: float


@dataclass
class OpenPosition:
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    timestamp: float
    status: str = "OPEN"
    setup_type: str = "unknown"
    trigger_level: Optional[float] = None


# Import the actual HFTExitManager logic (or a copy for testing)
# For this repro, I'll copy the logic to avoid import hell in this environment
class MockConfig:
    HFT_EXIT_MODE = True
    AXIA_INVALIDATION_ENABLED = True
    PATIENCE_LOCK_GRACE_PERIOD = 3.0
    CATASTROPHIC_STOP_PCT = 0.50
    HFT_AIRBAG_ENABLED = False


class HFTExitManagerTest:
    def __init__(self):
        self.logger = logging.getLogger("Test")
        self.patience_lock_grace_period = 3.0

    def _check_thesis_invalidation(self, position, event: TickEvent) -> bool:
        setup = position.setup_type
        if setup == "unknown":
            return False

        price = event.price

        if "Trapped_Traders" in setup:
            if position.trigger_level and position.trigger_level > 0:
                if position.side == "LONG" and price < position.trigger_level * 0.9995:
                    print(f"📉 [AXIA] Invalidation: Bears released at {price:.4f} (Trap: {position.trigger_level:.4f})")
                    return True
                if position.side == "SHORT" and price > position.trigger_level * 1.0005:
                    print(f"📈 [AXIA] Invalidation: Bulls released at {price:.4f} (Trap: {position.trigger_level:.4f})")
                    return True
        return False


def run_tests():
    manager = HFTExitManagerTest()

    # Test 1: Trapped Traders LONG (Bears Trapped at 100.0)
    pos_long = OpenPosition(
        trade_id="T1",
        symbol="LTCUSDT",
        side="LONG",
        entry_price=100.1,
        timestamp=0.0,
        setup_type="Trapped_Traders",
        trigger_level=100.0,
    )

    # Tick above trap (Valid)
    event_ok = TickEvent(symbol="LTCUSDT", price=100.01, timestamp=5.0)
    assert not manager._check_thesis_invalidation(pos_long, event_ok), "Should NOT invalidate above trap"

    # Tick below trap (Invalidated)
    event_fail = TickEvent(symbol="LTCUSDT", price=99.90, timestamp=5.0)
    assert manager._check_thesis_invalidation(pos_long, event_fail), "Should INVALIDATE below trap"

    # Test 2: Trapped Traders SHORT (Bulls Trapped at 110.0)
    pos_short = OpenPosition(
        trade_id="T2",
        symbol="LTCUSDT",
        side="SHORT",
        entry_price=109.9,
        timestamp=0.0,
        setup_type="Trapped_Traders",
        trigger_level=110.0,
    )

    # Tick below trap (Valid)
    event_ok_s = TickEvent(symbol="LTCUSDT", price=109.99, timestamp=5.0)
    assert not manager._check_thesis_invalidation(pos_short, event_ok_s), "Should NOT invalidate below trap"

    # Tick above trap (Invalidated)
    event_fail_s = TickEvent(symbol="LTCUSDT", price=110.10, timestamp=5.0)
    assert manager._check_thesis_invalidation(pos_short, event_fail_s), "Should INVALIDATE above trap"

    print("\n✅ All Axia Invalidation Unit Tests Passed!")


if __name__ == "__main__":
    run_tests()
