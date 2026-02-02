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

        # Ensure log directory exists
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        self.logger.info(f"📁 Audit Trail initialized at {self.log_path}")

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
        Records a decision event to the append-only log.
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

        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

            # Update in-memory buffer for TUI
            self.recent_decisions.append(entry)
            if len(self.recent_decisions) > 20:
                self.recent_decisions.pop(0)
        except Exception as e:
            self.logger.error(f"❌ Failed to write to audit trail: {e}")

        return trace_id

    def record_execution(self, trace_id: str, execution_details: Dict[str, Any]):
        """
        Updates an existing trace with execution results (fills, slippage, etc).
        For simplicity in Phase 103, we append a separate 'EXECUTION' record linked by trace_id.
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "unix_ts": time.time(),
            "trace_id": trace_id,
            "type": "EXECUTION_UPDATE",
            "details": execution_details,
        }

        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self.logger.error(f"❌ Failed to update audit trail: {e}")
