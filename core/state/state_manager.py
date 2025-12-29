"""
High-Level State Manager for Casino V3.

Coordinates state persistence across all components.

Author: Casino V3 Team
Version: 3.0.0
"""

import logging
from typing import Optional

from core.error_handling import RetryConfig, get_error_handler
from core.portfolio.balance_manager import BalanceManager
from core.portfolio.position_tracker import OpenPosition, PositionTracker

from .persistent_state import PersistentState, PositionState


class StateManager:
    """
    High-level state management coordinator.

    Responsibilities:
    - Initialize persistent state
    - Sync state between components (balance, positions, **statistics**)
    - Coordinate recovery
    - Provide unified state API
    - Trigger immediate saves on trade close

    Example:
        state_mgr = StateManager(
            position_tracker=tracker,
            balance_manager=balance_mgr,
            state_dir="./state"
        )

        await state_mgr.start()

        # Automatic state sync
        # Components update → StateManager syncs → PersistentState saves

        # Recovery
        recovered = await state_mgr.recover()
    """

    def __init__(
        self,
        position_tracker: PositionTracker,
        balance_manager: BalanceManager,
        state_dir: str = "./state",
        save_interval: int = 5,
        session_id: Optional[str] = None,
    ):
        """
        Initialize state manager.

        Args:
            position_tracker: PositionTracker instance
            balance_manager: BalanceManager instance
            state_dir: Directory for state files
            save_interval: Auto-save interval in seconds
            session_id: Session identifier
        """
        self.position_tracker = position_tracker
        self.balance_manager = balance_manager

        self.persistent_state = PersistentState(state_dir=state_dir, save_interval=save_interval, session_id=session_id)

        # Add ErrorHandler for resilient operations
        self.error_handler = get_error_handler()

        self.logger = logging.getLogger("StateManager")

    async def start(self, initial_balance: float):
        """
        Start state manager.

        Args:
            initial_balance: Initial balance for new session
        """
        # Initialize state
        self.persistent_state.initialize_state(initial_balance)

        # Start auto-save
        await self.persistent_state.start()

        self.logger.info("🚀 State manager started")

    async def stop(self):
        """Stop state manager and perform final sync."""
        # Sync current state
        await self.sync_to_persistent()

        # Stop auto-save
        await self.persistent_state.stop()

        self.logger.info("🛑 State manager stopped")

    async def sync_to_persistent(self):
        """Sync current component state to persistent storage with retry."""
        await self.error_handler.execute(
            self._do_sync_to_persistent,
            retry_config=RetryConfig(max_retries=2, backoff_base=0.5, backoff_factor=2.0),
            context="state_sync",
        )

    async def _do_sync_to_persistent(self):
        """Internal sync logic (called with retry wrapper)."""
        # Sync balance
        await self.persistent_state.update_balance(
            current=self.balance_manager.get_balance(),
            available=self.balance_manager.get_balance(),
            allocated=0.0,
        )

        # Sync stats
        tracker_stats = self.position_tracker.get_stats()
        await self.persistent_state.update_stats(
            total_trades=tracker_stats.get("total_closed", 0),
            total_wins=tracker_stats.get("total_wins", 0),
            total_losses=tracker_stats.get("total_losses", 0),
            total_opened=tracker_stats.get("total_opened", 0),
        )

        # Sync positions
        all_positions_state = []
        for position in self.position_tracker.open_positions:
            position_state = PositionState(
                trade_id=position.trade_id,
                symbol=position.symbol,
                side=position.side,
                entry_price=position.entry_price,
                entry_timestamp=position.entry_timestamp,
                margin_used=position.margin_used,
                notional=position.notional,
                amount=position.order.get("amount", 0.0) if position.order else 0.0,
                leverage=position.leverage,
                tp_level=position.tp_level,
                sl_level=position.sl_level,
                main_order_id=position.main_order_id,
                tp_order_id=position.tp_order_id,
                sl_order_id=position.sl_order_id,
                bars_held=position.bars_held,
                funding_accrued=position.funding_accrued,
                contributors=position.contributors or [],
                metadata={"order": position.order} if position.order else {},
            )
            all_positions_state.append(position_state)

        await self.persistent_state.set_open_positions(all_positions_state)

        self.logger.debug("💾 Synced state to persistent storage")

    async def sync_from_persistent(self):
        """Sync persistent state to components."""
        try:
            state = self.persistent_state.get_state()
            if not state:
                self.logger.warning("⚠️ No state to sync from")
                return

            # Sync balance
            self.balance_manager.set_balance(state.current_balance)

            # Sync stats
            self.position_tracker.set_stats(
                total_closed=state.total_trades,
                total_wins=state.total_wins,
                total_losses=state.total_losses,
                total_opened=state.total_opened,
            )

            # Sync positions
            self.position_tracker.open_positions = []
            for pos_state in state.open_positions:
                position = OpenPosition(
                    trade_id=pos_state.trade_id,
                    symbol=pos_state.symbol,
                    side=pos_state.side,
                    entry_price=pos_state.entry_price,
                    entry_timestamp=pos_state.entry_timestamp,
                    margin_used=pos_state.margin_used,
                    notional=pos_state.notional,
                    leverage=pos_state.leverage,
                    tp_level=pos_state.tp_level,
                    sl_level=pos_state.sl_level,
                    liquidation_level=None,  # Will be recalculated
                    # Use saved order from metadata (v2.1+) or fallback to amount/reconstruction (v2.0)
                    order=(
                        pos_state.metadata.get("order")
                        if pos_state.metadata and "order" in pos_state.metadata
                        else {
                            "amount": (
                                pos_state.amount
                                if pos_state.amount > 0
                                else (
                                    abs(pos_state.notional) / pos_state.entry_price
                                    if pos_state.entry_price > 0 and pos_state.notional
                                    else 0
                                )
                            )
                        }
                    ),
                    main_order_id=pos_state.main_order_id,
                    tp_order_id=pos_state.tp_order_id,
                    sl_order_id=pos_state.sl_order_id,
                    bars_held=pos_state.bars_held,
                    funding_accrued=pos_state.funding_accrued,
                    contributors=pos_state.contributors,
                )
                # Use add_position to ensure counters (recovered_count, total_opened) are updated
                self.position_tracker.add_position(position)

            self.logger.info(
                f"✅ Synced state from persistent storage: "
                f"{len(state.open_positions)} positions, "
                f"balance={state.current_balance:.2f}"
            )

        except Exception as e:
            self.logger.error(f"❌ Failed to sync from persistent state: {e}", exc_info=True)

    async def recover(self) -> bool:
        """
        Recover state from disk with retry.

        Returns:
            True if recovery successful, False otherwise
        """
        try:
            return await self.error_handler.execute(
                self._do_recover,
                retry_config=RetryConfig(max_retries=3, backoff_base=1.0, backoff_factor=2.0),
                context="state_recovery",
            )
        except Exception as e:
            self.logger.error(f"❌ State recovery failed after retries: {e}", exc_info=True)
            return False

    async def _do_recover(self) -> bool:
        """Internal recovery logic (called with retry wrapper)."""
        # Attempt recovery
        state = await self.persistent_state.recover()

        if state:
            # Sync to components
            await self.sync_from_persistent()

            # Start auto-save
            await self.persistent_state.start()

            self.logger.info(
                f"✅ State recovered successfully: "
                f"session={state.session_id}, "
                f"positions={len(state.open_positions)}, "
                f"balance={state.current_balance:.2f}"
            )
            return True
        else:
            self.logger.warning("⚠️ No state found to recover")
            return False

    def get_stats(self):
        """Get state statistics."""
        return self.persistent_state.get_stats()
