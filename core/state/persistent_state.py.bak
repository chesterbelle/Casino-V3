"""
Persistent State Management for Casino V3.

Provides automatic state persistence to disk with:
- Auto-save every N seconds
- Atomic writes (write to temp, then rename)
- JSON serialization
- Corruption detection
- Automatic recovery
- **Persistent statistics** (total trades, wins, losses)

Author: Casino V3 Team
Version: 3.0.0
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PositionState:
    """State of an open position."""

    trade_id: str
    symbol: str
    side: str
    entry_price: float
    entry_timestamp: str
    margin_used: float
    notional: float
    leverage: float
    tp_level: float
    sl_level: float
    main_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    bars_held: int = 0
    funding_accrued: float = 0.0
    contributors: List[str] = field(default_factory=list)


@dataclass
class BotState:
    """Complete bot state for persistence."""

    # Session info
    session_id: str
    start_time: float
    last_update: float

    # Balance
    initial_balance: float
    current_balance: float
    available_balance: float
    allocated_balance: float

    # Positions
    open_positions: List[PositionState] = field(default_factory=list)

    # Statistics
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0

    # Reconciliation
    last_reconciliation: Optional[float] = None

    # Metadata
    version: str = "2.0.0"


class PersistentState:
    """
    Manages persistent state with automatic sync to disk.

    Features:
    - Auto-save every N seconds
    - Atomic writes (temp file + rename)
    - JSON serialization
    - Corruption detection
    - Backup rotation (keep last N states)

    Example:
        state_mgr = PersistentState(
            state_dir="./state",
            save_interval=5,
            backup_count=10
        )

        await state_mgr.start()

        # Update state
        await state_mgr.update_balance(10000.0, 8000.0)
        await state_mgr.add_position(position)

        # State is auto-saved every 5 seconds

        # Recovery
        state = await state_mgr.recover()
    """

    def __init__(
        self,
        state_dir: str = "./state",
        save_interval: int = 5,
        backup_count: int = 10,
        session_id: Optional[str] = None,
    ):
        """
        Initialize persistent state manager.

        Args:
            state_dir: Directory to store state files
            save_interval: Seconds between auto-saves
            backup_count: Number of backups to keep
            session_id: Session identifier (auto-generated if None)
        """
        self.state_dir = Path(state_dir)
        self.save_interval = save_interval
        self.backup_count = backup_count
        self.session_id = session_id or f"session_{int(time.time())}"

        self.state_dir.mkdir(parents=True, exist_ok=True)

        self._state: Optional[BotState] = None
        self._dirty = False
        self._save_task: Optional[asyncio.Task] = None
        self._running = False

        self.logger = logging.getLogger("PersistentState")

    @property
    def state_file(self) -> Path:
        """Get path to current state file."""
        return self.state_dir / f"{self.session_id}.json"

    @property
    def temp_file(self) -> Path:
        """Get path to temporary state file."""
        return self.state_dir / f"{self.session_id}.json.tmp"

    def initialize_state(self, initial_balance: float) -> BotState:
        """
        Initialize new state.

        Args:
            initial_balance: Starting balance

        Returns:
            New BotState instance
        """
        self._state = BotState(
            session_id=self.session_id,
            start_time=time.time(),
            last_update=time.time(),
            initial_balance=initial_balance,
            current_balance=initial_balance,
            available_balance=initial_balance,
            allocated_balance=0.0,
            total_trades=0,
            total_wins=0,
            total_losses=0,
        )
        self._dirty = True
        self.logger.info(f"📝 Initialized new state: {self.session_id}")
        return self._state

    async def start(self):
        """Start auto-save background task."""
        if self._running:
            self.logger.warning("⚠️ State manager already running")
            return

        self._running = True
        self._save_task = asyncio.create_task(self._auto_save_loop())
        self.logger.info(f"🚀 State manager started (auto-save every {self.save_interval}s)")

    async def stop(self):
        """Stop auto-save and perform final save."""
        self._running = False

        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass

        # Final save
        if self._dirty:
            await self.save()

        self.logger.info("🛑 State manager stopped")

    async def _auto_save_loop(self):
        """Background task to auto-save state."""
        while self._running:
            try:
                await asyncio.sleep(self.save_interval)

                if self._dirty:
                    await self.save()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"❌ Error in auto-save loop: {e}", exc_info=True)

    async def save(self):
        """
        Save state to disk atomically.

        Uses atomic write pattern:
        1. Write to temp file
        2. Rename temp to actual (atomic operation)
        """
        if self._state is None:
            self.logger.warning("⚠️ No state to save")
            return

        try:
            # Update timestamp
            self._state.last_update = time.time()

            # Serialize to JSON
            state_dict = asdict(self._state)

            # Write to temp file
            with open(self.temp_file, "w") as f:
                json.dump(state_dict, f, indent=2)

            # Atomic rename
            self.temp_file.replace(self.state_file)

            self._dirty = False

            # Rotate backups
            await self._rotate_backups()

            self.logger.debug(f"💾 State saved: {self.state_file.name}")

        except Exception as e:
            self.logger.error(f"❌ Failed to save state: {e}", exc_info=True)

    async def _rotate_backups(self):
        """Rotate backup files, keeping last N."""
        try:
            # Create backup
            backup_file = self.state_dir / f"{self.session_id}.backup_{int(time.time())}.json"
            if self.state_file.exists():
                import shutil

                shutil.copy2(self.state_file, backup_file)

            # Find all backups for this session
            backups = sorted(
                self.state_dir.glob(f"{self.session_id}.backup_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            # Remove old backups
            for old_backup in backups[self.backup_count :]:
                old_backup.unlink()
                self.logger.debug(f"🗑️ Removed old backup: {old_backup.name}")

        except Exception as e:
            self.logger.error(f"❌ Failed to rotate backups: {e}")

    async def recover(self) -> Optional[BotState]:
        """
        Recover state from disk.

        Tries in order:
        1. Current state file
        2. Latest backup
        3. Returns None if no state found

        Returns:
            Recovered BotState or None
        """
        # Try current state file
        if self.state_file.exists():
            try:
                state = await self._load_state_file(self.state_file)
                if state:
                    self._state = state
                    self._dirty = False
                    self.logger.info(f"✅ Recovered state from: {self.state_file.name}")
                    return state
            except Exception as e:
                self.logger.error(f"❌ Failed to load state file: {e}")

        # Try latest backup
        backups = sorted(
            self.state_dir.glob(f"{self.session_id}.backup_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for backup in backups:
            try:
                state = await self._load_state_file(backup)
                if state:
                    self._state = state
                    self._dirty = False
                    self.logger.warning(f"⚠️ Recovered state from backup: {backup.name}")
                    return state
            except Exception as e:
                self.logger.error(f"❌ Failed to load backup {backup.name}: {e}")

        self.logger.warning("⚠️ No state found to recover")
        return None

    async def _load_state_file(self, file_path: Path) -> Optional[BotState]:
        """Load and validate state from file."""
        try:
            with open(file_path, "r") as f:
                state_dict = json.load(f)

            # Validate version
            if state_dict.get("version") != "2.0.0":
                self.logger.warning(f"⚠️ State version mismatch: {state_dict.get('version')}")

            # Convert positions
            positions = [PositionState(**p) for p in state_dict.get("open_positions", [])]
            state_dict["open_positions"] = positions

            # Create BotState
            state = BotState(**state_dict)

            return state

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Corrupted state file {file_path.name}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"❌ Error loading state file {file_path.name}: {e}")
            return None

    # --- State Update Methods ---

    async def update_balance(self, current: float, available: float, allocated: float = 0.0):
        """Update balance information."""
        if self._state:
            self._state.current_balance = current
            self._state.available_balance = available
            self._state.allocated_balance = allocated
            self._dirty = True

    async def update_stats(self, total_trades: int, total_wins: int, total_losses: int):
        """Update trade statistics."""
        if self._state:
            self._state.total_trades = total_trades
            self._state.total_wins = total_wins
            self._state.total_losses = total_losses
            self._dirty = True

    async def add_position(self, position: PositionState):
        """Add open position to state."""
        if self._state:
            # Remove if exists (update)
            self._state.open_positions = [p for p in self._state.open_positions if p.trade_id != position.trade_id]
            # Add new
            self._state.open_positions.append(position)
            self._dirty = True

    async def remove_position(self, trade_id: str):
        """Remove position from state."""
        if self._state:
            self._state.open_positions = [p for p in self._state.open_positions if p.trade_id != trade_id]
            self._dirty = True

    async def update_reconciliation_time(self):
        """Update last reconciliation timestamp."""
        if self._state:
            self._state.last_reconciliation = time.time()
            self._dirty = True

    def get_state(self) -> Optional[BotState]:
        """Get current state."""
        return self._state

    def get_stats(self) -> Dict[str, Any]:
        """Get state statistics."""
        if not self._state:
            return {"status": "no_state"}

        return {
            "session_id": self._state.session_id,
            "uptime_seconds": time.time() - self._state.start_time,
            "last_update": datetime.fromtimestamp(self._state.last_update).isoformat(),
            "open_positions_count": len(self._state.open_positions),
            "current_balance": self._state.current_balance,
            "available_balance": self._state.available_balance,
            "allocated_balance": self._state.allocated_balance,
            "total_trades": self._state.total_trades,
            "total_wins": self._state.total_wins,
            "total_losses": self._state.total_losses,
            "last_reconciliation": (
                datetime.fromtimestamp(self._state.last_reconciliation).isoformat()
                if self._state.last_reconciliation
                else None
            ),
            "dirty": self._dirty,
        }
