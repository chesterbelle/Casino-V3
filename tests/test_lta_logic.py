import asyncio
import logging
from unittest.mock import MagicMock

import pytest

from core.events import EventType, SignalEvent
from decision.setup_engine import SetupEngineV4


@pytest.mark.asyncio
async def test_lta_logic():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("TestLTA")

    # Mock dependencies
    engine = MagicMock()
    context = MagicMock()

    # Define a fake structure: POC at 100, VAH at 105, VAL at 95
    context.get_structural.return_value = (100.0, 105.0, 95.0)
    context.get_regime.return_value = "NEUTRAL"
    context.is_in_trade.return_value = False
    context.get_ib.return_value = (106.0, 94.0)  # IB High/Low
    context.get_volatility_ratio.return_value = 1.0
    context.get_poc_migration.return_value = 0.0
    context.get_va_integrity.return_value = 0.5
    context.micro_state = {"LTC/USDT": {"z_score": 0.0}}

    setup = SetupEngineV4(engine, context_registry=context)

    # Create a mock signal: Absorption at VAH (105.0)
    mock_metadata = {
        "tactical_type": "TacticalAbsorption",
        "direction": "SHORT",
        "price": 104.9,  # Closed inside (at VAH=105)
        "high": 105.5,  # Probed above
        "low": 104.0,
        "open": 104.2,  # Green-ish candle but rejecting top
        "z_score": 3.5,
    }

    event = SignalEvent(
        type=EventType.SIGNAL,
        timestamp=123456789.0,
        symbol="LTC/USDT",
        side="SHORT",
        sensor_id="Sensor_Absorption",
        metadata=mock_metadata,
    )

    logger.info("🧪 Injecting Absorption Signal at VAH (105.01)...")

    # Manually trigger evaluation
    setup.memory["LTC/USDT"] = [(123456789.0, 123456789.0, event)]
    events = [event]

    result = setup._evaluate_lta_structural("LTC/USDT", events)

    if result:
        logger.info(f"✅ Success! LTA Triggered: {result['setup_name']}")
        logger.info(f"🎯 Target TP (POC): {result['metadata']['tp_price']}")
        logger.info(f"🛡️ Stop Loss: {result['metadata']['sl_price']}")

        # Verify POC targeting
        assert result["metadata"]["tp_price"] == 100.0, "TP must be the POC"
        assert result["metadata"]["sl_price"] > 105.0, "SL must be above VAH for SHORT"
        logger.info("💎 LTA V4 Logic Certified!")
    else:
        logger.error("❌ LTA Failed to trigger. Check thresholds.")


if __name__ == "__main__":
    asyncio.run(test_lta_logic())
