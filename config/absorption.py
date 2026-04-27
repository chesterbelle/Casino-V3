"""
Absorption Scalping V1 Configuration

Strategy: Detect institutional absorption (exhaustion) and trade the reversal.
Edge: Captures institutional order flow exhaustion with high-frequency precision.

Phase 2.3: Initial configuration (baseline parameters)
"""

# ============================================================================
# ABSORPTION DETECTOR - Quality Filters
# ============================================================================

# Magnitude Filter: Z-score threshold for extreme delta
# Higher = more selective (only extreme absorption events)
ABSORPTION_MIN_Z_SCORE = 3.0  # Baseline: 3.0 (3 std deviations)

# Velocity Filter: Concentration threshold (% of delta in < 30s)
# Higher = faster absorption required (more institutional)
ABSORPTION_MIN_CONCENTRATION = 0.70  # Baseline: 70% of delta in < 30s

# Noise Filter: Maximum counter-delta allowed
# Lower = cleaner absorption (less noise)
ABSORPTION_MAX_NOISE = 0.20  # Baseline: 20% counter-delta

# Throttling: Minimum time between analysis (ms)
# Prevents IPC explosion from tick flood
ABSORPTION_ANALYSIS_THROTTLE_MS = 100  # Baseline: 100ms (10 Hz)

# ============================================================================
# ABSORPTION SETUP ENGINE - Confirmation Filters
# ============================================================================

# CVD Flattening: Maximum CVD slope after absorption
# Lower = stricter (CVD must flatten completely)
ABSORPTION_CVD_SLOPE_THRESHOLD = 5.0  # Baseline: 5.0

# Price Holding: Maximum distance from absorption level (%)
# Lower = stricter (price must hold near level)
ABSORPTION_PRICE_HOLD_THRESHOLD_PCT = 0.05  # Baseline: 0.05% (5 bps)

# Price Hold Window: Time window to check price holding (seconds)
ABSORPTION_PRICE_HOLD_WINDOW_SEC = 5.0  # Baseline: 5 seconds

# ============================================================================
# ABSORPTION SETUP ENGINE - TP/SL Configuration
# ============================================================================

# TP Distance: Minimum and maximum TP distance (%)
# TP is calculated dynamically based on first low-volume node (LVN)
ABSORPTION_MIN_TP_DISTANCE_PCT = 0.10  # Baseline: 0.10% (10 bps)
ABSORPTION_MAX_TP_DISTANCE_PCT = 0.50  # Baseline: 0.50% (50 bps)

# SL Buffer: Multiplier for SL distance based on delta magnitude
# Higher = wider SL (more room for noise)
ABSORPTION_SL_BUFFER_MULTIPLIER = 1.5  # Baseline: 1.5x delta magnitude

# SL Conversion: Delta to price distance conversion
# Simplified: 1 delta = 0.01% price move (to be calibrated)
ABSORPTION_DELTA_TO_PRICE_PCT = 0.0001  # Baseline: 1 delta = 0.01%

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

# ============================================================================
# OPTIMIZATION NOTES
# ============================================================================

# Phase 7 (Optimization):
# - Adjust ABSORPTION_MIN_Z_SCORE based on win rate (higher = more selective)
# - Adjust ABSORPTION_MIN_CONCENTRATION based on timeout rate (higher = faster moves)
# - Adjust ABSORPTION_MAX_NOISE based on false signals (lower = cleaner)
# - Adjust ABSORPTION_MIN_TP_DISTANCE_PCT based on MFE analysis
# - Adjust ABSORPTION_MAX_TP_DISTANCE_PCT based on timeout rate
# - Adjust ABSORPTION_SL_BUFFER_MULTIPLIER based on MAE analysis

# Expected ranges after optimization:
# - ABSORPTION_MIN_Z_SCORE: 3.0 - 4.0
# - ABSORPTION_MIN_CONCENTRATION: 0.70 - 0.80
# - ABSORPTION_MAX_NOISE: 0.15 - 0.25
# - ABSORPTION_MIN_TP_DISTANCE_PCT: 0.08 - 0.12
# - ABSORPTION_MAX_TP_DISTANCE_PCT: 0.20 - 0.30
# - ABSORPTION_SL_BUFFER_MULTIPLIER: 1.5 - 2.5
