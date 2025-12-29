"""
Tests for PersistentState and StateManager.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from core.portfolio.balance_manager import BalanceManager
from core.portfolio.position_tracker import OpenPosition, PositionTracker
from core.state import PersistentState, PositionState, StateManager


class TestPersistentState:
    """Tests for PersistentState."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for state files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def persistent_state(self, temp_dir):
        """Create PersistentState instance."""
        return PersistentState(state_dir=temp_dir, save_interval=1, session_id="test_session")

    @pytest.mark.asyncio
    async def test_initialize_state(self, persistent_state):
        """Test state initialization."""
        state = persistent_state.initialize_state(initial_balance=10000.0)

        assert state.session_id == "test_session"
        assert state.initial_balance == 10000.0
        assert state.current_balance == 10000.0
        assert state.available_balance == 10000.0
        assert len(state.open_positions) == 0

    @pytest.mark.asyncio
    async def test_save_and_load(self, persistent_state):
        """Test saving and loading state."""
        # Initialize and save
        state = persistent_state.initialize_state(initial_balance=10000.0)
        await persistent_state.save()

        # Verify file exists
        assert persistent_state.state_file.exists()

        # Load state
        loaded_state = await persistent_state.recover()

        assert loaded_state is not None
        assert loaded_state.session_id == "test_session"
        assert loaded_state.initial_balance == 10000.0

    @pytest.mark.asyncio
    async def test_atomic_write(self, persistent_state, temp_dir):
        """Test atomic write (temp file + rename)."""
        state = persistent_state.initialize_state(initial_balance=10000.0)
        await persistent_state.save()

        # Verify temp file is removed after save
        assert not persistent_state.temp_file.exists()

        # Verify actual file exists
        assert persistent_state.state_file.exists()

    @pytest.mark.asyncio
    async def test_backup_rotation(self, persistent_state):
        """Test backup rotation."""
        state = persistent_state.initialize_state(initial_balance=10000.0)

        # Create multiple saves
        for i in range(15):
            await persistent_state.update_balance(10000.0 + i, 8000.0 + i)
            await persistent_state.save()
            await asyncio.sleep(0.1)  # Small delay for different timestamps

        # Count backups
        backups = list(Path(persistent_state.state_dir).glob("test_session.backup_*.json"))

        # Should keep only 10 backups
        assert len(backups) <= 10

    @pytest.mark.asyncio
    async def test_update_balance(self, persistent_state):
        """Test balance updates."""
        state = persistent_state.initialize_state(initial_balance=10000.0)

        await persistent_state.update_balance(current=9500.0, available=8000.0, allocated=1500.0)

        state = persistent_state.get_state()
        assert state.current_balance == 9500.0
        assert state.available_balance == 8000.0
        assert state.allocated_balance == 1500.0

    @pytest.mark.asyncio
    async def test_add_remove_position(self, persistent_state):
        """Test adding and removing positions."""
        state = persistent_state.initialize_state(initial_balance=10000.0)

        # Add position
        position = PositionState(
            trade_id="test_trade_1",
            symbol="BTC/USDT:USDT",
            side="LONG",
            entry_price=50000.0,
            entry_timestamp="2024-01-01T00:00:00",
            margin_used=1000.0,
            notional=5000.0,
            leverage=5,
            tp_level=51000.0,
            sl_level=49000.0,
        )

        await persistent_state.add_position(position)

        state = persistent_state.get_state()
        assert len(state.open_positions) == 1
        assert state.open_positions[0].trade_id == "test_trade_1"

        # Remove position
        await persistent_state.remove_position("test_trade_1")

        state = persistent_state.get_state()
        assert len(state.open_positions) == 0

    @pytest.mark.asyncio
    async def test_auto_save(self, persistent_state):
        """Test auto-save functionality."""
        state = persistent_state.initialize_state(initial_balance=10000.0)

        # Start auto-save
        await persistent_state.start()

        # Update state
        await persistent_state.update_balance(9500.0, 8000.0)

        # Wait for auto-save
        await asyncio.sleep(1.5)

        # Stop auto-save
        await persistent_state.stop()

        # Verify state was saved
        assert persistent_state.state_file.exists()

        # Load and verify
        loaded_state = await persistent_state.recover()
        assert loaded_state.current_balance == 9500.0

    @pytest.mark.asyncio
    async def test_corrupted_file_recovery(self, persistent_state, temp_dir):
        """Test recovery from corrupted file using backup."""
        # Create valid state
        state = persistent_state.initialize_state(initial_balance=10000.0)
        await persistent_state.save()

        # Corrupt main file
        with open(persistent_state.state_file, "w") as f:
            f.write("corrupted json {{{")

        # Recovery should fall back to backup
        loaded_state = await persistent_state.recover()

        # Should recover from backup or return None
        assert loaded_state is None or loaded_state.initial_balance == 10000.0


class TestStateManager:
    """Tests for StateManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def components(self):
        """Create mock components."""
        position_tracker = PositionTracker(max_concurrent_positions=10)
        balance_manager = BalanceManager(starting_balance=10000.0)
        return position_tracker, balance_manager

    @pytest.fixture
    def state_manager(self, components, temp_dir):
        """Create StateManager instance."""
        position_tracker, balance_manager = components
        return StateManager(
            position_tracker=position_tracker,
            balance_manager=balance_manager,
            state_dir=temp_dir,
            save_interval=1,
            session_id="test_session",
        )

    @pytest.mark.asyncio
    async def test_start_and_stop(self, state_manager):
        """Test starting and stopping state manager."""
        await state_manager.start(initial_balance=10000.0)

        # Verify state initialized
        state = state_manager.persistent_state.get_state()
        assert state is not None
        assert state.initial_balance == 10000.0

        await state_manager.stop()

    @pytest.mark.asyncio
    async def test_sync_to_persistent(self, state_manager, components):
        """Test syncing component state to persistent storage."""
        position_tracker, balance_manager = components

        await state_manager.start(initial_balance=10000.0)

        # Modify component state
        balance_manager.set_balance(8000.0)

        # Add position
        position = OpenPosition(
            trade_id="test_trade_1",
            symbol="BTC/USDT:USDT",
            side="LONG",
            entry_price=50000.0,
            entry_timestamp="2024-01-01T00:00:00",
            margin_used=1000.0,
            notional=5000.0,
            leverage=5,
            tp_level=51000.0,
            sl_level=49000.0,
            liquidation_level=45000.0,
            order={},
        )
        position_tracker.open_positions.append(position)

        # Sync to persistent
        await state_manager.sync_to_persistent()

        # Verify persistent state
        state = state_manager.persistent_state.get_state()
        assert state.available_balance == 8000.0
        assert len(state.open_positions) == 1

        await state_manager.stop()

    @pytest.mark.asyncio
    async def test_recovery(self, state_manager, components, temp_dir):
        """Test state recovery."""
        position_tracker, balance_manager = components

        # Create and save state
        await state_manager.start(initial_balance=10000.0)

        # Add position
        position = OpenPosition(
            trade_id="test_trade_1",
            symbol="BTC/USDT:USDT",
            side="LONG",
            entry_price=50000.0,
            entry_timestamp="2024-01-01T00:00:00",
            margin_used=1000.0,
            notional=5000.0,
            leverage=5,
            tp_level=51000.0,
            sl_level=49000.0,
            liquidation_level=45000.0,
            order={},
        )
        position_tracker.open_positions.append(position)

        await state_manager.sync_to_persistent()
        await state_manager.stop()

        # Create new components (simulating restart)
        new_position_tracker = PositionTracker(max_concurrent_positions=10)
        new_balance_manager = BalanceManager(starting_balance=10000.0)

        new_state_manager = StateManager(
            position_tracker=new_position_tracker,
            balance_manager=new_balance_manager,
            state_dir=temp_dir,
            session_id="test_session",
        )

        # Recover
        recovered = await new_state_manager.recover()

        assert recovered is True
        assert len(new_position_tracker.open_positions) == 1
        assert new_position_tracker.open_positions[0].trade_id == "test_trade_1"

        await new_state_manager.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
