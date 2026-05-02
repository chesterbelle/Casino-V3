from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class GuardianResult:
    passed: bool
    multiplier: float = 1.0
    reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    gate_name: str = ""
