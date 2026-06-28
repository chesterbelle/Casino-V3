#!/usr/bin/env python3
"""
Cluster Optimizer — Bayesian Parameter Search for Casino-V3
============================================================

Full-featured optimizer using EdgeAuditor for evaluation.

Components:
  1. Bayesian Optimization (Optuna TPE sampler)
  2. Per-sensor parameter space with ranges
  3. Profile generation via PYTHONPATH injection
  4. Cross-coin validation
  5. Sensitivity analysis
  6. CPU limit (50% of host cores)
  7. Multi-criteria scoring (Net Taker + MFE/MAE + root cause)
  8. Statistical significance checks (min N signals)

Usage:
    python scripts/cluster_optimizer.py --cluster THIN_VOLATILE --coin XRPUSDT --iterations 50
    python scripts/cluster_optimizer.py --cluster MID_LIQUID --coin LTCUSDT --iterations 100
    python scripts/cluster_optimizer.py --cluster THIN_VOLATILE --validate-only
"""

import argparse
import copy
import glob
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_python = os.path.join(_BASE, ".venv", "bin", "python")
DB_DIR = os.path.join(_BASE, "data", "datasets", "daily_backtest_ready")


def set_low_priority():
    """Set nice=10 and ionice best-effort -n6 on worker processes."""
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        subprocess.run(
            ["ionice", "-c2", "-n6", "-p", str(os.getpid())],
            capture_output=True,
            check=False,
        )
    except Exception:
        pass


def get_memory_status():
    """Return RAM + swap usage status string."""
    if not HAS_PSUTIL:
        return "N/A"
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return f"RAM: {mem.percent}% | Swap: {swap.percent}%"
    except Exception:
        return "N/A"


def calculate_workers(min_workers: int, total_tasks: int) -> int:
    """Dynamically calculate safe worker count based on host resources."""
    host_cores = os.cpu_count() or 4
    cpu_workers = max(1, int(host_cores * 0.65))

    if HAS_PSUTIL:
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            avail_ram_gb = mem.available / (1024**3)
            avail_swap_gb = swap.free / (1024**3)
            total_avail_gb = avail_ram_gb + avail_swap_gb
            mem_workers = max(1, int(total_avail_gb * 0.65 / 0.6))
        except Exception:
            mem_workers = cpu_workers
    else:
        mem_workers = cpu_workers

    safe_workers = min(cpu_workers, mem_workers)
    return max(min_workers, min(safe_workers, total_tasks))


RESULTS_DIR = os.path.join(_BASE, "results")
LOG_DIR = os.path.join(_BASE, "logs")
TASK_TIMEOUT = 86400

MIN_SIGNALS_FOR_SIGNIFICANCE = 20
FEE_TAKER_RT = 0.07


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class AuditMetrics:
    net_taker: float = 0.0
    gross_expectancy: float = 0.0
    total_signals: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    root_cause: str = "NO_DATA"
    best_static_grids: Dict = field(default_factory=dict)
    setup_count: int = 0
    avg_mfe: float = 0.0
    avg_mae: float = 0.0
    mfe_mae_ratio: float = 0.0
    success: bool = False


@dataclass
class TrialResult:
    number: int
    params: Dict[str, Any]
    score: float
    metrics: AuditMetrics
    cluster: str


# ============================================================================
# Module 1: Cluster & Dataset Loading
# ============================================================================


def load_cluster_config() -> Dict:
    with open(os.path.join(_BASE, "config", "clusters_fixed.json")) as f:
        return json.load(f)


def get_cluster_members(cluster_name: str) -> List[str]:
    config = load_cluster_config()
    return config["clusters"].get(cluster_name, {}).get("members", [])


def get_datasets_for_symbol(symbol: str, filter_pattern: Optional[str] = None) -> List[str]:
    clean_sym = symbol.replace("/USDT:USDT", "").replace("USDT", "")
    pattern = os.path.join(DB_DIR, f"*{clean_sym}*.db")
    files = glob.glob(pattern)
    if filter_pattern:
        files = [f for f in files if filter_pattern in f]
    return [os.path.basename(f) for f in sorted(files)]


def format_ccxt_symbol(sym: str) -> str:
    if "/" in sym:
        return sym
    if sym.endswith("USDT"):
        return f"{sym[:-4]}/USDT:USDT"
    return sym


# ============================================================================
# Module 2: Parameter Space
# ============================================================================

PARAMETER_SPACE = {
    # Failed Breakout - Strict region + permissive margin
    "sensors.failed_breakout.exhaustion_z": (2.0, 4.0, 0.1),
    "sensors.failed_breakout.divergence_z": (0.5, 2.0, 0.1),
    "sensors.failed_breakout.min_break_distance_pct": (0.001, 0.006, 0.0002),
    "sensors.failed_breakout.cooldown": (30.0, 90.0, 5.0),
    "sensors.failed_breakout.max_break_age": (100.0, 180.0, 10.0),
    # Liquidity Exhaustion
    "sensors.liquidity_exhaustion.declining_threshold": (0.5, 0.98, 0.01),
    "sensors.liquidity_exhaustion.min_tests": (2, 5, 1),
    "sensors.liquidity_exhaustion.min_bounce_pct": (0.0001, 0.002, 0.00005),
    "sensors.liquidity_exhaustion.test_memory_seconds": (60.0, 300.0, 10.0),
    "sensors.liquidity_exhaustion.level_tolerance_pct": (0.0002, 0.001, 0.00005),
    # Trend Acceptance
    "sensors.trend_acceptance.cooldown": (120.0, 900.0, 30.0),
    "sensors.trend_acceptance.min_candles_outside": (2, 8, 1),
    "sensors.trend_acceptance.cvd_confirmation_threshold": (1.0, 5.0, 0.5),
    "sensors.trend_acceptance.max_pullback_penetration_pct": (0.001, 0.003, 0.0001),
    "sensors.trend_acceptance.pullback_tolerance_pct": (0.0005, 0.002, 0.0001),
    # Guardians
    "guardians.l2_ratio_min_trend_acceptance": (1.0, 2.0, 0.1),
    # Tactical Absorption - All params + expanded ranges (sensor name: absorption_detector)
    "sensors.absorption_detector.z_score_min": (2.0, 6.0, 0.1),
    "sensors.absorption_detector.cooldown": (30.0, 240.0, 10.0),
    "sensors.absorption_detector.level_tolerance_pct": (0.0005, 0.005, 0.0002),
    "sensors.absorption_detector.absorption_score_min": (0.05, 0.5, 0.025),
    "sensors.absorption_detector.book_bucket_pct": (0.0005, 0.003, 0.00025),
    "sensors.absorption_detector.displacement_z_max": (1.5, 4.0, 0.1),
    "sensors.absorption_detector.stagnation_floor_pct": (0.0002, 0.002, 0.0001),
    "sensors.absorption_detector.volatility_z_max": (1.5, 4.0, 0.1),
}


def filter_parameter_space(only: Optional[str]) -> Dict:
    """Return only the params for a specific scenario, or the full space."""
    if only is None:
        return PARAMETER_SPACE.copy()
    # Map scenario names to sensor prefixes
    sensor_map = {
        "failed_breakout": "failed_breakout",
        "liquidity_exhaustion": "liquidity_exhaustion",
        "trend_acceptance": "trend_acceptance",
        "tactical_absorption": "absorption_detector",
    }
    sensor_prefix = sensor_map.get(only, only)
    pref_sensors = f"sensors.{sensor_prefix}"
    pref_targets = f"targets.{only}"
    filtered = {k: v for k, v in PARAMETER_SPACE.items() if k.startswith(pref_sensors) or k.startswith(pref_targets)}
    # Include guardian params that belong to trend_acceptance
    if only == "trend_acceptance":
        guardian_key = "guardians.l2_ratio_min_trend_acceptance"
        if guardian_key in PARAMETER_SPACE:
            filtered[guardian_key] = PARAMETER_SPACE[guardian_key]
    return filtered


def apply_params_to_profile(base_profile: Dict, overrides: Dict[str, Any]) -> Dict:
    profile = copy.deepcopy(base_profile)
    for key, value in overrides.items():
        parts = key.split(".")
        d = profile
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return profile


# (profile overrides are injected via OPT_PROFILE_OVERRIDES env var — no file generation needed)


# ============================================================================
# Module 4: Backtest Runner (subprocess)
# ============================================================================


def run_backtest(db_path: str, symbol: str, overrides: Optional[Dict[str, Any]], task_id: str) -> Optional[str]:
    """Run backtest, return historian DB path on success.

    If overrides is provided, serializes to JSON and passes via
    OPT_PROFILE_OVERRIDES env var for profile_manager to apply.
    """
    historian_db = os.path.join(_BASE, "data", f"histan_opt_{task_id}.db")
    log_file = os.path.join(LOG_DIR, f"opt_{task_id}.log")

    cmd = [
        venv_python,
        "-u",
        "backtest.py",
        "--depth-db-path",
        db_path,
        "--run-type",
        "audit",
        "--symbol",
        symbol,
        "--historian-db",
        historian_db,
    ]

    env = os.environ.copy()
    env["CASINO_HISTORIAN_DB"] = historian_db
    if overrides:
        env["OPT_PROFILE_OVERRIDES"] = json.dumps(overrides)
    for var in [
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ]:
        env[var] = "1"

    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        with open(log_file, "w") as f:
            proc = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=_BASE, preexec_fn=set_low_priority
            )
            proc.wait(timeout=TASK_TIMEOUT)
        if proc.returncode == 0 and os.path.exists(historian_db):
            return historian_db
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception:
        pass
    return None


# ============================================================================
# Module 5: EdgeAuditor Integration
# ============================================================================


def evaluate_with_auditor(historian_db: str) -> AuditMetrics:
    """Run EdgeAuditor.get_metrics() and return structured metrics."""
    sys.path.insert(0, os.path.join(_BASE, "utils"))
    try:
        from setup_edge_auditor import EdgeAuditor

        auditor = EdgeAuditor(historian_db)
        raw = auditor.get_metrics()

        # Extract MFE/MAE from raw data if available
        avg_mfe = 0.0
        avg_mae = 0.0
        mfe_mae_ratio = 0.0

        signals, prices, _ = auditor.load_data()
        if not signals.empty:
            import numpy as np

            mfe_list = []
            mae_list = []
            for _, sig in signals.iterrows():
                entry_price = sig["price"]
                side = sig["side"]
                setup_type = sig["setup_type"]
                if entry_price <= 0:
                    continue
                from trajectory_core import get_trajectory

                win = auditor.SETUP_WINDOWS.get(setup_type, 14400)
                trajectory = get_trajectory(sig, prices, win)
                if trajectory.empty:
                    continue
                prices_list = trajectory["price"].values
                if side == "LONG":
                    mfe = (np.max(prices_list) - entry_price) / entry_price * 100
                    mae = (entry_price - np.min(prices_list)) / entry_price * 100
                else:
                    mfe = (entry_price - np.min(prices_list)) / entry_price * 100
                    mae = (np.max(prices_list) - entry_price) / entry_price * 100
                mfe_list.append(mfe)
                mae_list.append(mae)

            if mfe_list:
                avg_mfe = sum(mfe_list) / len(mfe_list)
                avg_mae = sum(mae_list) / len(mae_list)
                mfe_mae_ratio = avg_mfe / (avg_mae + 1e-9)

        return AuditMetrics(
            net_taker=raw.get("net_taker", 0.0),
            gross_expectancy=raw.get("gross_expectancy", 0.0),
            total_signals=raw.get("total_signals", 0),
            wins=raw.get("wins", 0),
            losses=raw.get("losses", 0),
            win_rate=raw.get("win_rate", 0.0),
            root_cause=raw.get("root_cause", "UNKNOWN"),
            best_static_grids=raw.get("best_static_grids", {}),
            setup_count=raw.get("setup_count", 0),
            avg_mfe=avg_mfe,
            avg_mae=avg_mae,
            mfe_mae_ratio=mfe_mae_ratio,
            success=True,
        )
    except Exception as e:
        return AuditMetrics(root_cause=f"ERROR: {e}")
    finally:
        sys.path.pop(0)


# ============================================================================
# Module 6: Composite Scoring
# ============================================================================


def compute_composite_score(metrics: AuditMetrics, only: Optional[str] = None) -> float:
    """
    Hybrid scoring: aligns with production (AMT net_taker) while preserving
    theoretical best_static_grid as directional guide.
    """
    # Scenario-specific minimum signals (per dataset, 3-regime average)
    SCENARIO_MIN_SIGNALS = {
        "failed_breakout": 3,
        "tactical_absorption": 5,
        "liquidity_exhaustion": 8,
        "trend_acceptance": 3,
    }
    min_signals = SCENARIO_MIN_SIGNALS.get(only, MIN_SIGNALS_FOR_SIGNIFICANCE if only is None else 10)
    if not metrics.success or metrics.total_signals < min_signals:
        return -100.0

    if only is not None:
        # Single-scenario: best_static_grid for that setup + overall net_taker as proxy
        setup_data = metrics.best_static_grids.get(only)
        if setup_data is None:
            return -50.0
        best_exp = setup_data["exp"] - FEE_TAKER_RT
        net_proxy = metrics.net_taker
        ratio_comp = min(metrics.mfe_mae_ratio - 1.0, 1.0)
        signal_comp = min(metrics.total_signals / 100.0, 1.0)
        penalty = -0.5 if best_exp < 0 else 0.0

        score = best_exp * 0.50 + net_proxy * 0.25 + ratio_comp * 0.15 + signal_comp * 0.10 + penalty * 0.10
    else:
        # Multi-scenario: overall net_taker primary + avg best_static_grid across ALL setups
        all_total = 0.0
        all_count = 0
        for setup, data in metrics.best_static_grids.items():
            if setup in ("failed_breakout", "liquidity_exhaustion", "trend_acceptance", "tactical_absorption"):
                all_total += data["exp"] - FEE_TAKER_RT
                all_count += 1
        avg_best_exp = all_total / all_count if all_count > 0 else 0.0
        penalty = -0.3 if (all_count > 0 and avg_best_exp < 0) else 0.0

        net_comp = metrics.net_taker
        ratio_comp = min(metrics.mfe_mae_ratio - 1.0, 1.0)
        signal_comp = min(metrics.total_signals / 100.0, 1.0)

        score = net_comp * 0.50 + avg_best_exp * 0.25 + ratio_comp * 0.15 + signal_comp * 0.10 + penalty * 0.10
    return score


# ============================================================================
# Module 7: Sensitivity Analysis
# ============================================================================


def run_sensitivity_analysis(
    study,
    cluster: str,
    representative: str,
    datasets: List[str],
    filter_pattern: Optional[str],
    active_space: Optional[Dict] = None,
):
    """Test each best parameter independently to measure sensitivity."""
    print("\n📊 Sensitivity Analysis (top 5 params)...")
    best = study.best_params

    # Sort trials by value, get top params
    sorted_trials = sorted(study.trials, key=lambda t: t.value if t.value else -999, reverse=True)
    if len(sorted_trials) < 3:
        return

    # Get most varied params from top trials
    param_importance = {}
    for key in best.keys():
        values = [t.params.get(key) for t in sorted_trials[:10] if t.params.get(key) is not None]
        if values:
            variance = max(values) - min(values)
            param_importance[key] = variance

    top_params = sorted(param_importance.keys(), key=lambda k: param_importance[k], reverse=True)[:5]

    sensitivity = {}
    _space = active_space or PARAMETER_SPACE
    for param_key in top_params:
        if param_key not in _space:
            continue
        low, high, step = _space[param_key]
        variation_pct = (param_importance[param_key] / (high - low)) * 100 if (high - low) > 0 else 0
        sensitivity[param_key] = {
            "range": param_importance[param_key],
            "variation_pct": variation_pct,
            "impact": "HIGH" if variation_pct > 30 else ("MEDIUM" if variation_pct > 15 else "LOW"),
        }
        icon = "🔴" if variation_pct > 30 else ("🟡" if variation_pct > 15 else "🟢")
        print(f"   {icon} {param_key}: {variation_pct:.0f}% range used ({sensitivity[param_key]['impact']})")

    return sensitivity


# ============================================================================
# Module 8: Cross-Coin Validation
# ============================================================================


def validate_cross_coin(cluster: str, best_params: Dict[str, Any], filter_pattern: Optional[str]) -> Dict[str, Any]:
    """Validate best params across all coins in cluster."""
    members = get_cluster_members(cluster)
    print(f"\n🔍 Cross-coin validation ({len(members)} coins)...")

    overrides_payload = {cluster: best_params} if best_params else None
    results = {}
    for symbol in members:
        datasets = get_datasets_for_symbol(symbol, filter_pattern)
        if not datasets:
            continue

        # Use first dataset per coin
        db_path = os.path.join(DB_DIR, datasets[0])
        safe_sym = symbol.replace("/", "_")
        task_id = f"val_{safe_sym}_{datasets[0].replace('.db', '')}"
        ccxt = format_ccxt_symbol(symbol)

        hist_db = run_backtest(db_path, ccxt, overrides_payload, task_id)
        if hist_db:
            metrics = evaluate_with_auditor(hist_db)
            results[symbol] = {
                "net_taker": metrics.net_taker,
                "root_cause": metrics.root_cause,
                "total_signals": metrics.total_signals,
                "mfe_mae_ratio": metrics.mfe_mae_ratio,
            }
            icon = "✅" if metrics.net_taker > 0 else "❌"
            print(
                f"   {icon} {symbol}: NT {metrics.net_taker:+.4f}% | Ratio {metrics.mfe_mae_ratio:.2f} | {metrics.root_cause}"
            )
        else:
            results[symbol] = {"net_taker": 0, "root_cause": "FAILED"}
            print(f"   ❌ {symbol}: Backtest failed")

    if results:
        avg_nt = sum(r["net_taker"] for r in results.values()) / len(results)
        passed = sum(1 for r in results.values() if r["net_taker"] > 0)
    else:
        avg_nt = 0
        passed = 0

    return {
        "coins": results,
        "cluster_avg_net_taker": avg_nt,
        "coins_passed": passed,
        "coins_total": len(results),
        "passed": passed >= len(results) * 0.5 and avg_nt > 0,
    }


# ============================================================================
# Module 9: Output Generation
# ============================================================================


def generate_output(
    cluster: str,
    best_params: Dict,
    best_score: float,
    baseline_metrics: AuditMetrics,
    validation: Dict,
    sensitivity: Dict,
    all_trials: List[Dict],
    optimization_time: float,
    output_path: Optional[str],
):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    sys.path.insert(0, os.path.join(_BASE, "config"))
    from coin_profiles import COIN_PROFILES, DEFAULT_PROFILE

    sys.path.pop(0)

    modified = copy.deepcopy(COIN_PROFILES)
    if cluster in modified:
        modified[cluster] = apply_params_to_profile(modified[cluster], best_params)

    if output_path is None:
        output_path = os.path.join(_BASE, "config", f"coin_profiles_{cluster}_optimized.py")

    with open(output_path, "w") as f:
        f.write(f'"""\nOptimized for {cluster}\nGenerated by cluster_optimizer.py\n"""\n\n')
        f.write(f"COIN_PROFILES = {json.dumps(modified, indent=4)}\n\n")
        f.write(f'DEFAULT_PROFILE = "{DEFAULT_PROFILE}"\n')

    json_path = os.path.join(RESULTS_DIR, f"opt_{cluster}_{int(time.time())}.json")
    with open(json_path, "w") as f:
        json.dump(
            {
                "cluster": cluster,
                "optimization_time_seconds": optimization_time,
                "best_score": best_score,
                "baseline": {
                    "net_taker": baseline_metrics.net_taker,
                    "root_cause": baseline_metrics.root_cause,
                    "mfe_mae_ratio": baseline_metrics.mfe_mae_ratio,
                    "total_signals": baseline_metrics.total_signals,
                },
                "best_params": best_params,
                "validation": validation,
                "sensitivity": sensitivity,
                "top_trials": sorted(all_trials, key=lambda x: x["score"], reverse=True)[:10],
            },
            f,
            indent=2,
            default=str,
        )

    print(f"\n{'='*60}")
    print(f"📊 RESULTS — {cluster}")
    print(f"{'='*60}")
    print("\nBaseline:")
    print(f"  Net Taker:    {baseline_metrics.net_taker:+.4f}%")
    print(f"  MFE/MAE:      {baseline_metrics.mfe_mae_ratio:.2f}")
    print(f"  Root Cause:   {baseline_metrics.root_cause}")
    print(f"  Signals:      {baseline_metrics.total_signals}")
    print("\nOptimized:")
    print(f"  Score:        {best_score:+.4f}")
    print("\nBest params:")
    for k, v in best_params.items():
        current = _get_current_param(cluster, k)
        delta = f" (was {current})" if current is not None and current != v else ""
        print(f"  {k}: {v}{delta}")
    if validation:
        print("\nCross-coin validation:")
        print(f"  Avg Net Taker: {validation['cluster_avg_net_taker']:+.4f}%")
        print(f"  Passed: {validation['coins_passed']}/{validation['coins_total']}")
    if sensitivity:
        print("\nSensitivity (top params):")
        for k, v in sensitivity.items():
            print(f"  {k}: {v['impact']} ({v['variation_pct']:.0f}% range)")
    print(f"\nOutput: {output_path}")
    print(f"Details: {json_path}")
    print(f"{'='*60}")


def _get_current_param(cluster: str, param_key: str):
    sys.path.insert(0, os.path.join(_BASE, "config"))
    from coin_profiles import COIN_PROFILES

    sys.path.pop(0)
    parts = param_key.split(".")
    value = COIN_PROFILES.get(cluster, {})
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def get_safe_workers(max_workers: Optional[int] = None, total_tasks: int = 1) -> int:
    if max_workers is not None:
        return max_workers
    host_cores = os.cpu_count() or 4
    cpu_workers = max(1, int(host_cores * 0.65))

    if HAS_PSUTIL:
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            avail_ram_gb = mem.available / (1024**3)
            avail_swap_gb = swap.free / (1024**3)
            total_avail_gb = avail_ram_gb + avail_swap_gb
            mem_workers = max(1, int(total_avail_gb * 0.65 / 0.6))
        except Exception:
            mem_workers = cpu_workers
    else:
        mem_workers = cpu_workers

    safe_workers = min(cpu_workers, mem_workers)
    return max(1, min(safe_workers, total_tasks))


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Cluster Optimizer — Bayesian Parameter Search for Casino-V3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cluster",
        required=True,
        choices=[
            "MEGA_LIQUID",
            "MAJOR_LIQUID",
            "MID_LIQUID",
            "THIN_VOLATILE",
            "ILLIQUID_SPEC",
            "SOL_INERTIAL_TRENDING",
            "AVAX_NOISY_UNCERTAIN",
            "LTC_NOISY_UNCERTAIN_1",
            "INERTIAL_TRENDING",
            "NOISY_UNCERTAIN",
            "NOISY_UNCERTAIN_1",
        ],
    )
    parser.add_argument("--coin", help="Representative coin")
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        choices=["failed_breakout", "liquidity_exhaustion", "trend_acceptance", "tactical_absorption"],
        help="Optimizar solo un escenario. Filtra PARAMETER_SPACE y scoring a ese escenario.",
    )
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument(
        "--min-workers", type=int, default=1, help="Minimum worker floor (dynamic calc based on RAM/CPU)"
    )
    parser.add_argument("--filter", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--sensitivity", action="store_true", default=True)
    parser.add_argument("--study-db", type=str, default=None, help="SQLite DB for persistent study (survives cancel)")
    parser.add_argument("--resume", action="store_true", help="Resume existing study from --study-db")
    args = parser.parse_args()

    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    workers = calculate_workers(min_workers=args.min_workers, total_tasks=args.iterations)
    members = get_cluster_members(args.cluster)
    if not members:
        print(f"❌ Cluster {args.cluster} not found")
        sys.exit(1)

    representative = args.coin or members[0]
    datasets = get_datasets_for_symbol(representative, args.filter)
    if not datasets:
        print(f"❌ No datasets for {representative}")
        sys.exit(1)

    # Use 3 regime-fixed datasets (UP + DOWN + BALANCE) for robust evaluation
    up_dbs = sorted([d for d in datasets if "TREND_UP" in d])
    down_dbs = sorted([d for d in datasets if "TREND_DOWN" in d])
    balance_dbs = sorted([d for d in datasets if "BALANCE" in d])
    opt_datasets = []
    for pool in [up_dbs, down_dbs, balance_dbs]:
        if pool:
            opt_datasets.append(pool[-1])

    print(f"\n🔧 CLUSTER OPTIMIZER — {args.cluster}")
    if args.only:
        print(f"   Focus:        {args.only} (single-scenario mode)")
    print(f"   Representative: {representative}")
    print(f"   Members: {members}")
    print("   Datasets (opt, 3 regime-fixed):")
    for d in opt_datasets:
        print(f"      • {d}")
    print(f"   Available datasets: {len(datasets)}")
    print(f"   Iterations: {args.iterations}")
    print(f"   Workers: {workers} (dynamic: {get_memory_status()})")

    # Filter parameter space if --only is set
    active_space = filter_parameter_space(args.only)
    if args.only and not active_space:
        print(f"❌ No params in PARAMETER_SPACE for scenario '{args.only}'. Add them or pick a different scenario.")
        sys.exit(1)
    if args.only:
        print(f"   Parameters:   {len(active_space)} ({', '.join(active_space.keys())})")

    sys.path.insert(0, os.path.join(_BASE, "config"))
    from coin_profiles import COIN_PROFILES

    sys.path.pop(0)
    base_profile = COIN_PROFILES.get(args.cluster, {})
    if not base_profile:
        print(f"❌ Cluster {args.cluster} not in coin_profiles.py")
        sys.exit(1)

    os.makedirs(RESULTS_DIR, exist_ok=True)

    symbol = format_ccxt_symbol(representative)

    # ── Baseline (averaged across 3 regime datasets) ──
    print("\n📏 BASELINE (current params, averaged across regimes)...")
    baseline_scores = []
    for i, db_name in enumerate(opt_datasets):
        db_path = os.path.join(DB_DIR, db_name)
        hist_db = run_backtest(db_path, symbol, None, f"baseline_{i}")
        if hist_db:
            m = evaluate_with_auditor(hist_db)
            baseline_scores.append(m)
            print(
                f"   [{db_name}] Net Taker: {m.net_taker:+.4f}% | MFE/MAE: {m.mfe_mae_ratio:.2f} | {m.root_cause} | Signals: {m.total_signals}"
            )
        else:
            baseline_scores.append(AuditMetrics(root_cause="BACKTEST_FAILED"))
            print(f"   [{db_name}] ❌ Backtest failed")

    # Clean up baseline historian DBs
    for i in range(len(opt_datasets)):
        try:
            os.remove(os.path.join(_BASE, "data", f"histan_opt_baseline_{i}.db"))
        except OSError:
            pass

    # Average baseline
    valid = [m for m in baseline_scores if m.success]
    if valid:
        baseline = AuditMetrics(
            net_taker=sum(m.net_taker for m in valid) / len(valid),
            gross_expectancy=sum(m.gross_expectancy for m in valid) / len(valid),
            total_signals=int(sum(m.total_signals for m in valid) / len(valid)),
            wins=int(sum(m.wins for m in valid) / len(valid)),
            losses=int(sum(m.losses for m in valid) / len(valid)),
            win_rate=sum(m.win_rate for m in valid) / len(valid),
            root_cause=(
                "EDGE_CONFIRMED"
                if sum(1 for m in valid if "EDGE" in m.root_cause) > len(valid) / 2
                else valid[-1].root_cause
            ),
            best_static_grids=valid[-1].best_static_grids,
            setup_count=valid[-1].setup_count,
            avg_mfe=sum(m.avg_mfe for m in valid) / len(valid),
            avg_mae=sum(m.avg_mae for m in valid) / len(valid),
            mfe_mae_ratio=sum(m.mfe_mae_ratio for m in valid) / len(valid),
            success=True,
        )
        print(
            f"\n   📊 BASELINE AVG: Net {baseline.net_taker:+.4f}% | MFE/MAE {baseline.mfe_mae_ratio:.2f} | Signals {baseline.total_signals}"
        )
    else:
        baseline = AuditMetrics(root_cause="BACKTEST_FAILED")
        print("   ❌ All baseline backtests failed")

    if args.validate_only:
        print("\nValidate-only mode. Using current params.")
        validation = validate_cross_coin(args.cluster, {}, args.filter)
        generate_output(args.cluster, {}, 0.0, baseline, validation, {}, [], 0.0, args.output)
        return

    # ── Bayesian Optimization ──
    def objective(trial):
        overrides = {}
        for key, (low, high, step) in active_space.items():
            if isinstance(low, int) and isinstance(high, int):
                overrides[key] = trial.suggest_int(key, low, high, step=step)
            else:
                overrides[key] = trial.suggest_float(key, low, high, step=step)

        overrides_payload = {args.cluster: overrides}
        scores = []
        for i, db_name in enumerate(opt_datasets):
            db_path = os.path.join(DB_DIR, db_name)
            safe_sym = symbol.replace("/", "_")
            task_id = f"{safe_sym}_{trial.number}_{i}"
            hist_db = run_backtest(db_path, symbol, overrides_payload, task_id)
            if not hist_db:
                return -100.0
            metrics = evaluate_with_auditor(hist_db)
            score = compute_composite_score(metrics, only=args.only)
            scores.append(score)
            try:
                os.remove(hist_db)
            except OSError:
                pass

            # Report intermediate value for pruning
            partial = sum(scores) / len(scores)
            trial.report(partial, i)
            if trial.should_prune():
                return partial

        avg_score = sum(scores) / len(scores)
        trial.set_user_attr("avg_score", avg_score)
        return avg_score

    # ── Study persistence ──
    study_db = args.study_db or os.path.join(RESULTS_DIR, f"study_{args.cluster}.db")
    storage = f"sqlite:///{study_db}"

    print(f"\n🚀 OPTIMIZATION ({args.iterations} iterations)...")
    if args.resume and os.path.exists(study_db):
        study = optuna.load_study(study_name=args.cluster, storage=storage)
        print(f"   📂 Resumed from {study_db} ({len(study.trials)} existing trials)")
    else:
        study = optuna.create_study(
            study_name=args.cluster,
            storage=storage,
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42, multivariate=True, group=True),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=1),
            load_if_exists=True,
        )
        print(f"   📁 Study DB: {study_db}")

    start = time.time()
    study.optimize(objective, n_trials=args.iterations, show_progress_bar=True, n_jobs=workers)
    elapsed = time.time() - start

    print(f"\n✅ Best score: {study.best_value:+.4f}")
    print(f"   📂 Results saved to {study_db} — cancel safely, use --resume to continue")

    # ── Collect trial results ──
    all_trials = []
    for t in study.trials:
        if t.value is not None:
            all_trials.append(
                {
                    "number": t.number,
                    "score": t.value,
                    "avg_score": t.user_attrs.get("avg_score", 0),
                }
            )

    # ── Sensitivity Analysis ──
    sensitivity = None
    if args.sensitivity:
        sensitivity = run_sensitivity_analysis(study, args.cluster, representative, datasets, args.filter, active_space)

    # ── Cross-Coin Validation ──
    validation = validate_cross_coin(args.cluster, study.best_params, args.filter)

    # ── Output ──
    generate_output(
        args.cluster,
        study.best_params,
        study.best_value,
        baseline,
        validation,
        sensitivity,
        all_trials,
        elapsed,
        args.output,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Cancelled.")
    except Exception as e:
        print(f"\n❌ FATAL: {e}")
        import traceback

        traceback.print_exc()
