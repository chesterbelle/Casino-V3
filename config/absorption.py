"""
Absorption Detector Configuration

Strategy: Detect institutional absorption (exhaustion) and trade the reversal.
Edge: Captures institutional order flow exhaustion with high-frequency precision.
"""

# ============================================================================
# ABSORPTION DETECTOR - Quality Filters
# ============================================================================

# Magnitude Filter: Z-score threshold for extreme delta
# Higher = more selective (only extreme absorption events)
ABSORPTION_MIN_Z_SCORE = 3.0  # Baseline: 3.0 (3 std deviations)

# Velocity Filter: Concentration threshold (% of delta in < 30s)
# Higher = faster absorption required (more institutional)
ABSORPTION_MIN_CONCENTRATION = 0.50  # 50% dominant volume

# Noise Filter: Maximum counter-delta allowed
# Lower = cleaner absorption (less noise)
ABSORPTION_MAX_NOISE = 0.35  # 35% counter-delta

# ============================================================================
# FOOTPRINT REGISTRY - Volume Profile Configuration
# ============================================================================

# Sliding Window: Time window for footprint data (minutes)
FOOTPRINT_WINDOW_MINUTES = 60  # Baseline: 60 minutes

# Pruning Interval: How often to prune old data (seconds)
FOOTPRINT_PRUNE_INTERVAL_SEC = 60  # Baseline: 60 seconds

# Volume Profile: LVN threshold (% of average volume)
# Lower = more LVNs detected (more TP candidates)
FOOTPRINT_LVN_THRESHOLD_PCT = 0.50  # Baseline: 50% of avg volume
