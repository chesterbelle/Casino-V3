import logging
import multiprocessing as mp
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional


def _auditor_worker(log_path: str, q: mp.Queue):
    """Background Multi-Process Worker for DecisionAuditor JSONL I/O."""
    import json
    import logging

    worker_logger = logging.getLogger("AuditorWorker")

    while True:
        try:
            entry = q.get()
            if entry is None:
                break

            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            worker_logger.error(f"AuditorWorker error processing entry: {e}")


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

        # Ensure log directory exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Phase 240: HFT Multiprocessing Decoupling
        self._queue = None
        self._worker_process = None

    def _ensure_worker(self):
        """Lazily starts the background worker process."""
        if self._worker_process is None:
            self._queue = mp.Queue()
            self._worker_process = mp.Process(
                target=_auditor_worker, args=(self.log_path, self._queue), name="AuditorWorker", daemon=True
            )
            self._worker_process.start()
            self.logger.info(f"🚀 AuditorWorker Process started for ultra-low latency I/O at {self.log_path}")

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
            self._ensure_worker()
            self._queue.put_nowait(entry)
        except Exception as e:
            self.logger.error(f"Failed to queue audit entry: {e}")

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
            self._ensure_worker()
            self._queue.put_nowait(entry)
        except Exception as e:
            self.logger.error(f"Failed to queue execution entry: {e}")
