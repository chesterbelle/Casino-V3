import sys

# Add workspace to path
sys.path.append("/home/chesterbelle/Casino-V3")
import decision.engine.quality_scorer as qs  # noqa: E402

print(f"Module path: {qs.__file__}")

from core.context_registry import ContextRegistry  # noqa: E402
from decision.engine.quality_scorer import _score_regime  # noqa: E402

reg = ContextRegistry()
reg.update_structural_from_session("TEST", 100, 110, 90, 1.0)
thresholds = {"excess_multiplier": 0.1}
signal = {"close": 115}

score, reason, mode, pos = _score_regime("TEST", "SHORT", signal, reg, thresholds)
print(f"Short pos (mult 0.1): {pos}")
