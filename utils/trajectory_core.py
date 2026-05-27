"""
Trajectory Core Module - Shared utilities for trajectory analysis
Corrected to align with the actual historian SQLite schema.
Enhanced for multi-level MFE sampling without look-ahead bias.
"""

import sqlite3
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def load_data(db_path: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load signals, price_samples, and decision_traces from historian database.
    Uses json_extract to pull metadata directly from the signals table.
    """
    conn = sqlite3.connect(db_path)

    # Load all signals with metadata extracted from JSON
    signals_query = """
    SELECT id, timestamp, symbol, side, price, metadata, session_id,
           json_extract(metadata, '$.scenario') as setup_type,
           json_extract(metadata, '$.z_score_entry') as z_score_entry,
           json_extract(metadata, '$.max_holding_time') as max_holding_time,
           json_extract(metadata, '$.tp_distance_pct') as tp_distance_pct,
           json_extract(metadata, '$.sl_distance_pct') as sl_distance_pct,
           json_extract(metadata, '$.tp_price') as tp_price,
           json_extract(metadata, '$.sl_price') as sl_price,
           json_extract(metadata, '$.poc_price') as poc_price,
           json_extract(metadata, '$.vwap_z_score') as vwap_z_score,
           json_extract(metadata, '$.footprint_z_score') as footprint_z_score,
           json_extract(metadata, '$.value_position') as value_position,
           json_extract(metadata, '$.value_acceptance') as value_acceptance,
           json_extract(metadata, '$.atr_1m') as atr_pct,
           json_extract(metadata, '$.is_composite') as is_composite,
           json_extract(metadata, '$.conviction_score') as conviction_score
    FROM signals
    ORDER BY timestamp
    """
    signals_df = pd.read_sql_query(signals_query, conn)

    # Clean up NaN values from JSON extracts
    numeric_cols = [
        "z_score_entry",
        "max_holding_time",
        "tp_distance_pct",
        "sl_distance_pct",
        "tp_price",
        "sl_price",
        "poc_price",
        "vwap_z_score",
        "footprint_z_score",
        "atr_pct",
        "conviction_score",
    ]
    for col in numeric_cols:
        if col in signals_df.columns:
            signals_df[col] = pd.to_numeric(signals_df[col], errors="coerce").fillna(0)

    # Load all price_samples
    price_samples_df = pd.read_sql_query("SELECT * FROM price_samples ORDER BY timestamp", conn)

    # Load decision_traces
    traces_df = pd.read_sql_query("SELECT * FROM decision_traces ORDER BY timestamp", conn)

    conn.close()
    return signals_df, price_samples_df, traces_df


def get_trajectory(signal_row: pd.Series, price_samples_df: pd.DataFrame, window_sec: int = 14400) -> pd.DataFrame:
    """
    Extract trajectory data for a single signal.
    Uses pandas filtering to align continuous global price_samples with the signal's
    symbol, entry price, and timestamp range.
    """
    sig_ts = signal_row["timestamp"]
    symbol = signal_row["symbol"]
    entry_price = signal_row["price"]
    side = signal_row["side"]

    # Filter for this symbol and within the window [sig_ts, sig_ts + window_sec]
    mask = (
        (price_samples_df["symbol"] == symbol)
        & (price_samples_df["timestamp"] >= sig_ts)
        & (price_samples_df["timestamp"] <= sig_ts + window_sec)
    )

    signal_data = price_samples_df.loc[mask].copy()

    if len(signal_data) == 0:
        return pd.DataFrame()

    # Sort by timestamp
    signal_data = signal_data.sort_values("timestamp")

    # Calculate elapsed time from signal entry
    signal_data["elapsed_seconds"] = signal_data["timestamp"] - sig_ts

    # Calculate MFE and MAE for trajectory analysis
    if side == "LONG":
        signal_data["mfe_pct"] = (signal_data["price"] - entry_price) / entry_price * 100
        signal_data["mae_pct_so_far"] = (entry_price - signal_data["price"].cummin()) / entry_price * 100
    else:  # SHORT
        signal_data["mfe_pct"] = (entry_price - signal_data["price"]) / entry_price * 100
        signal_data["mae_pct_so_far"] = (signal_data["price"].cummax() - entry_price) / entry_price * 100

    # Calculate max future MFE for each point (for t_stop detection)
    signal_data["max_future_mfe"] = signal_data["mfe_pct"].iloc[::-1].cummax().iloc[::-1]

    return signal_data


def calculate_t_stop(
    trajectory_df: pd.DataFrame, upside_dead_delta: float = 0.15, min_samples_after: int = 2
) -> Optional[float]:
    """
    Automatically detect t_stop when upside becomes dead.
    """
    if len(trajectory_df) == 0:
        return None

    # For each point, check if future MFE doesn't exceed current MFE + delta
    for i in range(len(trajectory_df) - min_samples_after):
        current_mfe = trajectory_df.iloc[i]["mfe_pct"]
        max_future = trajectory_df.iloc[i]["max_future_mfe"]

        if max_future <= current_mfe + upside_dead_delta:
            # Check next min_samples_after points confirm
            confirm_window = trajectory_df.iloc[i : i + min_samples_after]
            all_confirm = all(
                row["max_future_mfe"] <= row["mfe_pct"] + upside_dead_delta for _, row in confirm_window.iterrows()
            )

            if all_confirm:
                return trajectory_df.iloc[i]["timestamp"]

    return None  # Never stops within window


def extract_trajectory_features(
    trajectory_df: pd.DataFrame, signal_metadata: Dict, t_stop: Optional[float] = None
) -> Dict:
    """
    Extract features for rule evaluation around t_stop.
    """
    if len(trajectory_df) == 0:
        return {}

    features = {}

    # Basic trajectory stats
    features["total_samples"] = len(trajectory_df)
    features["max_mfe"] = trajectory_df["mfe_pct"].max()
    features["min_mae"] = trajectory_df["mae_pct_so_far"].min()
    features["final_mfe"] = trajectory_df.iloc[-1]["mfe_pct"]
    features["final_mae"] = trajectory_df.iloc[-1]["mae_pct_so_far"]

    # Peak analysis
    peak_idx = trajectory_df["mfe_pct"].idxmax()
    features["t_peak"] = trajectory_df.loc[peak_idx, "timestamp"]
    features["peak_mfe"] = trajectory_df.loc[peak_idx, "mfe_pct"]
    features["peak_elapsed"] = trajectory_df.loc[peak_idx, "elapsed_seconds"]

    # t-stop analysis
    if t_stop is not None:
        stop_data = trajectory_df[trajectory_df["timestamp"] == t_stop]
        if len(stop_data) > 0:
            features["t_stop"] = t_stop
            features["stop_elapsed"] = stop_data.iloc[0]["elapsed_seconds"]
            features["stop_mfe"] = stop_data.iloc[0]["mfe_pct"]
            features["stop_mae"] = stop_data.iloc[0]["mae_pct_so_far"]
            features["micro_z"] = stop_data.iloc[0].get("micro_z", None)
        else:
            features["t_stop"] = None
            features["stop_elapsed"] = trajectory_df.iloc[-1]["elapsed_seconds"]
            features["micro_z"] = trajectory_df.iloc[-1].get("micro_z", None)
    else:
        features["t_stop"] = None
        features["stop_elapsed"] = trajectory_df.iloc[-1]["elapsed_seconds"]
        features["micro_z"] = trajectory_df.iloc[-1].get("micro_z", None)

    # Signal context from metadata
    for key, value in signal_metadata.items():
        if pd.notna(value):
            features[f"signal_{key}"] = value

    return features


def extract_features_at_mfe_level(
    trajectory_df: pd.DataFrame,
    signal_metadata: Dict,
    target_mfe_fraction: float,  # e.g., 0.2 for 20% of eventual MFE
    max_available_mfe: float,  # Global max MFE of trajectory (used only for threshold calc)
) -> Optional[Dict]:
    """
    Extract features at the FIRST point where MFE >= target_mfe_fraction * max_available_mfe.
    Uses ONLY data available up to that point (zero look-ahead bias).

    Args:
        trajectory_df: DataFrame with columns ['timestamp', 'price', 'mfe_pct', ...]
                      sorted by timestamp ascending
        signal_metadata: Dict of signal metadata (known at t=0)
        target_mfe_fraction: Fraction of max_available_mfe to sample at (0.0-1.0)
        max_available_mfe: The maximum MFE achieved in the entire trajectory

    Returns:
        Dict of features at the sampling point, or None if threshold never reached
    """
    if trajectory_df.empty or max_available_mfe <= 0:
        return None

    # Calculate dynamic threshold based on eventual MFE (only for determining WHEN to sample)
    mfe_threshold = target_mfe_fraction * max_available_mfe

    # Find FIRST point where achieved MFE >= threshold
    # Using .iloc[0] to ensure we get the earliest crossing (real-time availability)
    mask = trajectory_df["mfe_pct"] >= mfe_threshold
    if not mask.any():
        return None  # Threshold never reached in this trajectory

    first_cross_idx = trajectory_df[mask].index[0]
    # ONLY use data UP TO AND INCLUDING this point (zero look-ahead)
    point_df = trajectory_df.loc[:first_cross_idx].copy()

    # Extract features using only available data at this point
    features = _extract_point_features(point_df, signal_metadata)
    features["mfe_level"] = target_mfe_fraction  # For analysis grouping
    features["elapsed_at_level"] = point_df.iloc[-1]["elapsed_seconds"]
    features["mfe_at_level"] = point_df.iloc[-1]["mfe_pct"]

    return features


def _extract_point_features(point_df: pd.DataFrame, signal_metadata: Dict) -> Dict:
    """
    Extract features from a trajectory point DataFrame (data available up to this point).
    This mirrors extract_trajectory_features but works on any point-in-time slice.
    """
    if len(point_df) == 0:
        return {}

    features = {}

    # Basic trajectory stats UP TO THIS POINT
    features["total_samples"] = len(point_df)
    features["max_mfe_so_far"] = point_df["mfe_pct"].max()
    features["min_mae_so_far"] = point_df["mae_pct_so_far"].min()
    features["final_mfe"] = point_df.iloc[-1]["mfe_pct"]
    features["final_mae"] = point_df.iloc[-1]["mae_pct_so_far"]

    # Peak analysis UP TO THIS POINT
    if len(point_df) > 0:
        peak_idx = point_df["mfe_pct"].idxmax()
        features["peak_mfe"] = point_df.loc[peak_idx, "mfe_pct"]
        features["peak_elapsed"] = point_df.loc[peak_idx, "elapsed_seconds"]
        features["time_since_peak"] = point_df.iloc[-1]["elapsed_seconds"] - point_df.loc[peak_idx, "elapsed_seconds"]
    else:
        features["peak_mfe"] = 0.0
        features["peak_elapsed"] = 0.0
        features["time_since_peak"] = 0.0

    # Microstructure analysis (if available in data)
    if "micro_z" in point_df.columns and not point_df["micro_z"].isna().all():
        # Use the most recent micro_z value available
        features["micro_z"] = point_df.iloc[-1]["micro_z"]
        features["micro_z_max"] = point_df["micro_z"].max()
        features["micro_z_min"] = point_df["micro_z"].min()

        # Calculate delta_z: deviation from entry microstructure
        # z_score_entry is stored in signal_metadata
        z_score_entry = signal_metadata.get("z_score_entry") or signal_metadata.get("footprint_z_score", 0)
        if z_score_entry is not None:
            try:
                z_score_entry = float(z_score_entry)
                current_micro_z = float(point_df.iloc[-1]["micro_z"])
                features["delta_z"] = abs(z_score_entry - current_micro_z)
                features["delta_z_signed"] = (
                    current_micro_z - z_score_entry
                )  # Positive = microstructure favors same direction as entry
                # Check if microstructure has crossed zero (changed direction)
                features["micro_z_crossed_zero"] = (z_score_entry * current_micro_z) < 0
                # Check if microstructure has returned toward zero (impulse fading)
                features["delta_z_from_entry"] = abs(current_micro_z) - abs(z_score_entry)
            except (ValueError, TypeError):
                features["delta_z"] = None
                features["delta_z_signed"] = None
                features["micro_z_crossed_zero"] = None
                features["delta_z_from_entry"] = None
        else:
            features["delta_z"] = None
            features["delta_z_signed"] = None
            features["micro_z_crossed_zero"] = None
            features["delta_z_from_entry"] = None
    else:
        features["micro_z"] = None
        features["micro_z_max"] = None
        features["micro_z_min"] = None
        features["delta_z"] = None
        features["delta_z_signed"] = None
        features["micro_z_crossed_zero"] = None
        features["delta_z_from_entry"] = None

    # Signal context from metadata (known at t=0)
    for key, value in signal_metadata.items():
        if pd.notna(value):
            features[f"signal_{key}"] = value

    return features


# Constants for window configuration (shared with setup_edge_auditor)
SETUP_WINDOWS = {
    "TacticalAbsorptionV2": 14400,
    "failed_breakout": 7200,
    "liquidity_exhaustion": 7200,
    "trend_acceptance": 14400,
}

DEFAULT_WINDOW = 14400  # 4 hours default
