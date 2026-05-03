import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TraceRegistry:
    """
    Singleton registry for TraceBullets.
    Used primarily during validation and stress tests.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TraceRegistry, cls).__new__(cls)
            cls._instance.traces = {}
            cls._instance.active = os.environ.get("TRACE_BULLET_ACTIVE", "0") == "1"
        return cls._instance

    def record(self, trace_id: str, component: str, border: str, data: Dict[str, Any]):
        if not self.active:
            return

        if trace_id not in self.traces:
            self.traces[trace_id] = []

        self.traces[trace_id].append({"timestamp": time.time(), "component": component, "border": border, "data": data})


class TraceBulletMixin:
    """
    Mixin to add TraceBullet capabilities to any component.
    Provides a standardized way to report internal state transitions.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._trace_registry = TraceRegistry()

    def trace(self, event: Any, border: str, extra_data: Optional[Dict[str, Any]] = None):
        """
        Reports a trace event if a trace_id is present in event metadata.
        """
        # Try to extract trace_id from different event formats (SignalEvent object or dict)
        trace_id = None
        if hasattr(event, "metadata") and isinstance(event.metadata, dict):
            trace_id = event.metadata.get("trace_id")
        elif isinstance(event, dict):
            # Check both top level and metadata level
            trace_id = event.get("trace_id") or event.get("metadata", {}).get("trace_id")

        if not trace_id:
            return

        # Prepare trace data
        data = {}
        if hasattr(event, "to_dict"):
            data = event.to_dict()
        elif isinstance(event, dict):
            data = event.copy()

        if extra_data:
            data.update(extra_data)

        component_name = getattr(self, "name", self.__class__.__name__)

        # 1. Record in registry (for validators)
        self._trace_registry.record(trace_id, component_name, border, data)

        # 2. Log specifically for trace debugging (Compact representation)
        data_summary = f" | {data.get('reason', '')} {data.get('gate', '')}" if data else ""
        logger.debug(f"🎯 [TRACE] {trace_id} | {component_name} | {border}{data_summary}")
