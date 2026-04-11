"""
Strategy Configuration - Phase 600 Pivot
Decouples strategy-specific logic from global trading configuration.
"""

# LTA V4: Structural Reversion Settings
LTA_PROXIMITY_THRESHOLD = 0.0025  # 0.25% distance from VA edges (VAH/VAL)
LTA_SL_TICK_BUFFER = 2.0  # Number of ticks beyond the edge for SL (proxy: 0.05% per tick)
LTA_TICK_PROXY = 0.0005  # 0.05% as a proxy for a single price tick

# Registry of active playbooks for SetupEngine
ACTIVE_STRATEGIES = ["LTA_STRUCTURAL"]
