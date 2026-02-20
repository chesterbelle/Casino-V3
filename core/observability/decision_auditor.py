import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional


class DecisionAuditor:
    """
    Forensic Audit Trail for Casino V3 (Phase 103).

    Records every micro-decision with market snapshots and unique trace IDs
    to enable post-trade behavioral analysis and slippage auditing.
    """

    def __init__(self, log_dir: str = "logs"):
        self.logger = logging.getLogger("DecisionAuditor")
        self.log_path = os.path.join(log_dir, "audit_trail.jsonl")
        self.recent_decisions = []
        self._queue = asyncio.Queue()
        self._worker_task = None

        # Ensure log directory exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        self.logger.info(f"📁 Audit Trail initialized at {self.log_path}")

    def _start_worker_if_needed(self):
        """Starts the background flush worker if not already running."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running() and (self._worker_task is None or self._worker_task.done()):
                self._worker_task = loop.create_task(self._flush_worker())
        except RuntimeError:
            pass  # No loop running

    async def _flush_worker(self):
        """Background task that writes queued entries to disk."""
        while True:
            try:
                entry = await self._queue.get()
                # Use a small batch or just append - for audit logs, immediate append is safer
                # but we do it in a way that doesn't block the loop.
                # Since we are in the worker task, we can afford the blocking write
                # OR better, offload it to a thread.
                await asyncio.get_event_loop().run_in_executor(None, self._write_to_disk, entry)
                self._queue.task_done()
            except Exception as e:
                self.logger.error(f"❌ Auditor worker error: {e}")
                await asyncio.sleep(1)

    def _write_to_disk(self, entry: Dict[str, Any]):
        """Synchronous file write intended to be run in an executor."""
        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self.logger.error(f"❌ Failed to write to audit trail disk: {e}")

    def record_decision(
        self,
        symbol: str,
        action: str,
        score: float,
        reason: str,
        snapshot: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> str:
        """
        Records a decision event. (Non-blocking)
        """
        if not trace_id:
            import uuid

            trace_id = f"trc_{uuid.uuid4().hex[:8]}"

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "unix_ts": time.time(),
            "trace_id": trace_id,
            "symbol": symbol,
            "action": action,
            "score": round(score, 4),
            "reason": reason,
            "market_snapshot": snapshot,
        }

        # Queue the entry
        try:
            self._queue.put_nowait(entry)
            self._start_worker_if_needed()
        except Exception:
            # Fallback to sync write if queue is full or other issues
            self._write_to_disk(entry)

        # Update in-memory buffer for TUI
        self.recent_decisions.append(entry)
        if len(self.recent_decisions) > 20:
            self.recent_decisions.pop(0)

        return trace_id

    def record_execution(self, trace_id: str, execution_details: Dict[str, Any]):
        """
        Updates an existing trace with execution results. (Non-blocking)
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "unix_ts": time.time(),
            "trace_id": trace_id,
            "type": "EXECUTION_UPDATE",
            "details": execution_details,
        }

        try:
            self._queue.put_nowait(entry)
            self._start_worker_if_needed()
        except Exception:
            self._write_to_disk(entry)
