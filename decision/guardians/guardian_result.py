from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class SetupMode(Enum):
    REVERSION = "reversion"
    CONTINUATION = "continuation"
    NEUTRAL = "neutral"


@dataclass
class GuardianResult:
    passed: bool  # Hard Gate: If False, the trade is REJECTED regardless of score
    score: float = 1.0  # Fuzzy Confidence: 0.0 to 1.0
    multiplier: float = 1.0  # Optional sizing multiplier for this specific guardian
    reason: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    gate_name: str = ""
    setup_mode: SetupMode = SetupMode.REVERSION  # V3: Classification of the opportunity
