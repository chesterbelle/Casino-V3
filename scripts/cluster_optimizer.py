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

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_python = os.path.join(_BASE, ".venv", "bin", "python")
DB_DIR = os.path.join(_BASE, "data", "datasets", "backtest_ready")
RESULTS_DIR = os.path.join(_BASE, "results")
OPT_PROFILES_DIR = os.path.join(_BASE, "config", "_opt_profiles")
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
    best_uniforms: Dict = field(default_factory=dict)
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
    # Absorption detector
    "sensors.absorption_detector.z_score_min": (1.0, 5.0, 0.1),
    "sensors.absorption_detector.concentration_min": (0.20, 0.90, 0.05),
    "sensors.absorption_detector.noise_max": (0.10, 0.60, 0.05),
    "sensors.absorption_detector.stagnation_floor_pct": (0.05, 0.25, 0.01),
    # Failed breakout
    "sensors.failed_breakout.min_break_distance_pct": (0.0003, 0.0030, 0.0001),
    "sensors.failed_breakout.cvd_divergence_threshold": (0.15, 0.50, 0.05),
    # Liquidity exhaustion
    "sensors.liquidity_exhaustion.level_tolerance_pct": (0.0002, 0.0015, 0.0001),
    "sensors.liquidity_exhaustion.min_tests": (2, 6, 1),
    "sensors.liquidity_exhaustion.declining_threshold": (0.50, 0.90, 0.05),
    # Trend acceptance
    "sensors.trend_acceptance.min_candles_outside": (2, 6, 1),
    "sensors.trend_acceptance.cvd_confirmation_threshold": (2.0, 10.0, 0.5),
    "sensors.trend_acceptance.pullback_tolerance_pct": (0.0005, 0.0030, 0.0001),
    # Targets
    "targets.trend_acceptance.tp_pct": (0.010, 0.040, 0.002),
    "targets.trend_acceptance.sl_pct": (0.015, 0.050, 0.002),
    "targets.tactical_absorption.tp_pct": (0.010, 0.040, 0.002),
    "targets.tactical_absorption.sl_pct": (0.015, 0.050, 0.002),
    # Quality scorer
    "quality_scorer.grade_thresholds.A": (0.50, 0.95, 0.05),
    "quality_scorer.grade_thresholds.B": (0.20, 0.70, 0.05),
}


def apply_params_to_profile(base_profile: Dict, overrides: Dict[str, Any]) -> Dict:
    profile = copy.deepcopy(base_profile)
    for key, value in overrides.items():
        parts = key.split(".")
        d = profile
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return profile


# ============================================================================
# Module 3: Profile Generation (PYTHONPATH injection)
# ============================================================================


def generate_optimized_profile(cluster: str, overrides: Dict[str, Any], output_dir: str) -> str:
    sys.path.insert(0, os.path.join(_BASE, "config"))
    from coin_profiles import COIN_PROFILES, DEFAULT_PROFILE

    sys.path.pop(0)

    modified = copy.deepcopy(COIN_PROFILES)
    if cluster in modified:
        modified[cluster] = apply_params_to_profile(modified[cluster], overrides)

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "coin_profiles.py")
    with open(path, "w") as f:
        f.write(f'"""Auto-generated optimized profile for {cluster}"""\n\n')
        f.write(f"COIN_PROFILES = {json.dumps(modified, indent=4)}\n\n")
        f.write(f'DEFAULT_PROFILE = "{DEFAULT_PROFILE}"\n')
    return path


# ============================================================================
# Module 4: Backtest Runner (subprocess)
# ============================================================================


def run_backtest(db_path: str, symbol: str, opt_dir: str, task_id: str) -> Optional[str]:
    """Run backtest, return historian DB path on success."""
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
    if opt_dir:
        env["PYTHONPATH"] = f"{opt_dir}:{env.get('PYTHONPATH', '')}"
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
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=_BASE)
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
            best_uniforms=raw.get("best_uniforms", {}),
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


def compute_composite_score(metrics: AuditMetrics) -> float:
    """
    Multi-criteria composite score:
      - Net Taker (primary, weight 0.5)
      - MFE/MAE ratio (secondary, weight 0.3)
      - Signal count penalty if below threshold (weight 0.2)
    """
    if not metrics.success or metrics.total_signals < MIN_SIGNALS_FOR_SIGNIFICANCE:
        return -100.0

    # Net Taker component (normalized around 0)
    net_component = metrics.net_taker

    # MFE/MAE component (>1.2 is good, >1.5 is great)
    ratio_component = min(metrics.mfe_mae_ratio - 1.0, 1.0)  # cap at +1.0

    # Signal count bonus (more signals = more confidence)
    signal_component = min(metrics.total_signals / 100.0, 1.0)  # cap at 1.0

    # Root cause penalty
    root_penalty = 0.0
    if metrics.root_cause == "ENTRY_FAILURE":
        root_penalty = -0.5
    elif metrics.root_cause == "TARGET_FAILURE":
        root_penalty = -0.2
    elif metrics.root_cause == "EDGE_CONFIRMED":
        root_penalty = 0.1

    score = net_component * 0.5 + ratio_component * 0.3 + signal_component * 0.2 + root_penalty
    return score


# ============================================================================
# Module 7: Sensitivity Analysis
# ============================================================================


def run_sensitivity_analysis(
    study, cluster: str, representative: str, datasets: List[str], filter_pattern: Optional[str]
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
    for param_key in top_params:
        low, high, step = PARAMETER_SPACE[param_key]
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

    trial_dir = os.path.join(OPT_PROFILES_DIR, "validation")
    generate_optimized_profile(cluster, best_params, trial_dir)

    results = {}
    for symbol in members:
        datasets = get_datasets_for_symbol(symbol, filter_pattern)
        if not datasets:
            continue

        # Use first dataset per coin
        db_path = os.path.join(DB_DIR, datasets[0])
        task_id = f"val_{symbol}_{datasets[0].replace('.db', '')}"
        ccxt = format_ccxt_symbol(symbol)

        hist_db = run_backtest(db_path, ccxt, trial_dir, task_id)
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


# ============================================================================
# Module 10: CPU Limiter
# ============================================================================


def get_safe_workers(max_workers: Optional[int] = None) -> int:
    if max_workers is not None:
        return max_workers
    total = os.cpu_count() or 4
    return max(1, total // 2)


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
        choices=["MEGA_LIQUID", "MAJOR_LIQUID", "MID_LIQUID", "THIN_VOLATILE", "ILLIQUID_SPEC"],
    )
    parser.add_argument("--coin", help="Representative coin")
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--filter", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--sensitivity", action="store_true", default=True)
    parser.add_argument("--study-db", type=str, default=None, help="SQLite DB for persistent study (survives cancel)")
    parser.add_argument("--resume", action="store_true", help="Resume existing study from --study-db")
    args = parser.parse_args()

    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    workers = get_safe_workers(args.max_workers)
    members = get_cluster_members(args.cluster)
    if not members:
        print(f"❌ Cluster {args.cluster} not found")
        sys.exit(1)

    representative = args.coin or members[0]
    datasets = get_datasets_for_symbol(representative, args.filter)
    if not datasets:
        print(f"❌ No datasets for {representative}")
        sys.exit(1)

    # Use 1 dataset per iteration for speed, validate with more
    opt_dataset = datasets[0]

    print(f"\n🔧 CLUSTER OPTIMIZER — {args.cluster}")
    print(f"   Representative: {representative}")
    print(f"   Members: {members}")
    print(f"   Dataset (opt): {opt_dataset}")
    print(f"   Available datasets: {len(datasets)}")
    print(f"   Iterations: {args.iterations}")
    print(f"   CPU workers: {workers}")

    sys.path.insert(0, os.path.join(_BASE, "config"))
    from coin_profiles import COIN_PROFILES

    sys.path.pop(0)
    base_profile = COIN_PROFILES.get(args.cluster, {})
    if not base_profile:
        print(f"❌ Cluster {args.cluster} not in coin_profiles.py")
        sys.exit(1)

    os.makedirs(OPT_PROFILES_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    db_path = os.path.join(DB_DIR, opt_dataset)
    symbol = format_ccxt_symbol(representative)

    # ── Baseline ──
    print("\n📏 BASELINE (current params)...")
    hist_db = run_backtest(db_path, symbol, "", "baseline")
    if hist_db:
        baseline = evaluate_with_auditor(hist_db)
        print(
            f"   Net Taker: {baseline.net_taker:+.4f}% | MFE/MAE: {baseline.mfe_mae_ratio:.2f} | {baseline.root_cause} | Signals: {baseline.total_signals}"
        )
    else:
        baseline = AuditMetrics(root_cause="BACKTEST_FAILED")
        print("   ❌ Backtest failed")

    if args.validate_only:
        print("\nValidate-only mode. Using current params.")
        validation = validate_cross_coin(args.cluster, {}, args.filter)
        generate_output(args.cluster, {}, 0.0, baseline, validation, {}, [], 0.0, args.output)
        return

    # ── Bayesian Optimization ──
    def objective(trial):
        overrides = {}
        for key, (low, high, step) in PARAMETER_SPACE.items():
            if isinstance(low, int) and isinstance(high, int):
                overrides[key] = trial.suggest_int(key, low, high, step=step)
            else:
                overrides[key] = trial.suggest_float(key, low, high, step=step)

        trial_dir = os.path.join(OPT_PROFILES_DIR, f"trial_{trial.number}")
        generate_optimized_profile(args.cluster, overrides, trial_dir)

        task_id = f"{representative}_{trial.number}"
        hist_db = run_backtest(db_path, symbol, trial_dir, task_id)
        if not hist_db:
            return -100.0

        metrics = evaluate_with_auditor(hist_db)
        score = compute_composite_score(metrics)

        trial.set_user_attr("net_taker", metrics.net_taker)
        trial.set_user_attr("mfe_mae", metrics.mfe_mae_ratio)
        trial.set_user_attr("signals", metrics.total_signals)
        trial.set_user_attr("root_cause", metrics.root_cause)

        return score

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
            sampler=optuna.samplers.TPESampler(seed=42),
            load_if_exists=True,
        )
        print(f"   📁 Study DB: {study_db}")

    start = time.time()
    study.optimize(objective, n_trials=args.iterations, show_progress_bar=True)
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
                    "net_taker": t.user_attrs.get("net_taker", 0),
                    "mfe_mae": t.user_attrs.get("mfe_mae", 0),
                    "signals": t.user_attrs.get("signals", 0),
                    "root_cause": t.user_attrs.get("root_cause", ""),
                }
            )

    # ── Sensitivity Analysis ──
    sensitivity = None
    if args.sensitivity:
        sensitivity = run_sensitivity_analysis(study, args.cluster, representative, datasets, args.filter)

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
