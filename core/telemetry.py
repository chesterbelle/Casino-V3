"""
Unified Decision DNA (UDT) - Casino-V3 Telemetry System.
High-performance, in-memory decision tracking for forensic analysis.
"""

import logging
import time
from collections import deque
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Telemetry")


class TraceOutcome(Enum):
    PENDING = "PENDING"
    DISCARDED = "DISCARDED"
    EXECUTED = "EXECUTED"
    ERROR = "ERROR"


class DecisionStep:
    def __init__(self, component: str, passed: bool, message: str, metadata: Optional[Dict] = None):
        self.timestamp = time.time()
        self.component = component
        self.passed = passed
        self.message = message
        self.metadata = metadata or {}


class DecisionTrace:
    """
    The 'DNA' of a trading decision.
    Travels through the Crystal Pipe capturing every gate evaluation.
    """

    def __init__(self, symbol: str, side: str, signal_id: str):
        self.trace_id = f"{symbol}_{int(time.time()*1000)}"
        self.signal_id = signal_id
        self.symbol = symbol
        self.side = side
        self.start_time = time.time()
        self.steps: List[DecisionStep] = []
        self.outcome = TraceOutcome.PENDING
        self.final_reason = ""
        self.metadata: Dict[str, Any] = {}

    def add_step(self, component: str, passed: bool, message: str, metadata: Optional[Dict] = None):
        """Add a forensic step to the trace."""
        step = DecisionStep(component, passed, message, metadata)
        self.steps.append(step)

        # Internal logging for extreme debug, but UDT is the primary source
        logger.debug(f"[UDT:{self.symbol}] {component} -> {'PASS' if passed else 'FAIL'}: {message}")

    def finalize(self, outcome: TraceOutcome, reason: str = ""):
        """Close the trace with a final outcome."""
        self.outcome = outcome
        self.final_reason = reason
        duration_ms = (time.time() - self.start_time) * 1000
        self.metadata["duration_ms"] = duration_ms

    def print_autopsy(self) -> str:
        """Returns a human-readable forensic report of the decision."""
        status_icon = "✅" if self.outcome == TraceOutcome.EXECUTED else "❌"
        if self.outcome == TraceOutcome.PENDING:
            status_icon = "⏳"

        report = [
            f"{status_icon} AUTOPSY REPORT: {self.trace_id}",
            f"Symbol: {self.symbol} | Side: {self.side} | Outcome: {self.outcome.value}",
            f"Reason: {self.final_reason}",
            "-" * 40,
        ]

        for i, step in enumerate(self.steps):
            mark = "✔️" if step.passed else "✖️"
            elapsed = (step.timestamp - self.start_time) * 1000
            report.append(f"{i+1:02d} | {elapsed:6.2f}ms | {mark} [{step.component}] {step.message}")
            if step.metadata:
                # Add compact metadata if relevant
                meta_str = str(step.metadata)[:100] + "..." if len(str(step.metadata)) > 100 else str(step.metadata)
                report.append(f"    └─ Data: {meta_str}")

        report.append("-" * 40)
        report.append(f"Total Processing Time: {self.metadata.get('duration_ms', 0):.2f}ms")
        return "\n".join(report)


class TraceRegistry:
    """
    The 'Black Box' - Stores and manages decision traces.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TraceRegistry, cls).__new__(cls)
            cls._instance.traces = deque(maxlen=2000)  # Store last 2000 decisions
            cls._instance.active_traces: Dict[str, DecisionTrace] = {}
            cls._instance.historian = None  # Reference to TradeHistorian
        return cls._instance

    def set_historian(self, historian):
        """Inject historian reference for persistence."""
        self.historian = historian

    def create_trace(self, symbol: str, side: str, signal_id: str) -> DecisionTrace:
        trace = DecisionTrace(symbol, side, signal_id)
        self.active_traces[trace.trace_id] = trace
        return trace

    def get_trace(self, trace_id: str) -> Optional[DecisionTrace]:
        return self.active_traces.get(trace_id)

    def archive_trace(self, trace_id: str):
        """Move an active trace to the historical buffer."""
        if trace_id in self.active_traces:
            trace = self.active_traces.pop(trace_id)
            self.traces.append(trace)

            # Log the autopsy if it resulted in an execution or error
            if trace.outcome in [TraceOutcome.EXECUTED, TraceOutcome.ERROR]:
                logger.info(f"\n{trace.print_autopsy()}")

            # Persist to Historian if available
            if self.historian:
                # For Edge Auditor, we record the final outcome of the trace
                # The auditor looks for 'status' and 'gate' to categorize edge
                # status = outcome, gate = setup_type or first step
                setup_type = "unknown"
                if trace.steps:
                    setup_type = trace.steps[0].component

                metrics = trace.metadata.copy()
                metrics["trace_id"] = trace.trace_id

                data = {
                    "timestamp": trace.start_time,
                    "symbol": trace.symbol,
                    "status": trace.outcome.value,
                    "gate": setup_type,
                    "reason": trace.final_reason,
                    "metrics": metrics,
                    "price": trace.metadata.get("price", 0.0),
                    "side": trace.side,
                }
                self.historian.record_decision_trace(data)


# Global instance for easy access
black_box = TraceRegistry()
