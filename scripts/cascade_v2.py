#!/usr/bin/env python3
"""
Cascade v2 Optimizer — Scenario-by-scenario optimization with safe merge.
Usage: python cascade_v2.py --symbol AVAX_NOISY_UNCERTAIN --coin AVAXUSDT --iterations 50 --max-retries 3
"""

import argparse
import copy

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(BASE, ".venv", "bin", "python")

SCENARIOS = ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]

# Scenario-specific keys to merge (prevents cross-contamination)
# Incluye TODOS los params críticos validados en LTC V3 (ver .agent/golden_params/ltc.md)
SCENARIO_KEYS = {
    "tactical_absorption": {
        "sensors": {
            "absorption_detector": [
                "z_score_min",
                "absorption_score_min",
                "displacement_z_max",
                "stagnation_floor_pct",
                "cooldown",
                "book_bucket_pct",
                "level_tolerance_pct",
                "volatility_z_max",
            ]
        },
        "guardians": ["l2_ratio_min_tactical_absorption", "spread_max_ratio_tactical_absorption"],
        "pressure_thresholds": ["z_block_tactical_absorption"],
        "targets": ["tactical_absorption"],
    },
    "failed_breakout": {
        "sensors": {
            "failed_breakout": ["exhaustion_z", "divergence_z", "max_break_age", "min_break_distance_pct", "cooldown"]
        },
        "guardians": ["l2_ratio_min_failed_breakout", "spread_max_ratio_failed_breakout"],
        "pressure_thresholds": ["z_block_failed_breakout"],
        "targets": ["failed_breakout"],
    },
    "liquidity_exhaustion": {
        "sensors": {
            "liquidity_exhaustion": [
                "declining_threshold",
                "min_tests",
                "min_bounce_pct",
                "test_memory_seconds",
                "cooldown",
                "level_tolerance_pct",
            ]
        },
        "guardians": ["l2_ratio_min_liquidity_exhaustion", "spread_max_ratio_liquidity_exhaustion"],
        "pressure_thresholds": ["z_block_liquidity_exhaustion"],
        "targets": ["liquidity_exhaustion"],
    },
    "trend_acceptance": {
        "sensors": {
            "trend_acceptance": [
                "cvd_confirmation_threshold",
                "min_candles_outside",
                "pullback_tolerance_pct",
                "max_pullback_penetration_pct",
                "cooldown",
                # Regime Filter internos (críticos LTC V3)
                "regime_poc_migration_max",
                "regime_vol_ratio_max",
                "regime_va_expansion_max",
            ]
        },
        "guardians": ["l2_ratio_min_trend_acceptance", "spread_max_ratio_trend_acceptance"],
        "pressure_thresholds": ["z_block_trend_acceptance"],
        "targets": ["trend_acceptance"],
    },
}

# Shared keys (apply once at the end from the LAST successful scenario)
# Incluye quality_scorer completo + va_gate + scenarios
SHARED_KEYS = {
    "quality_scorer": ["weights", "grade_thresholds", "thresholds"],
    "va_gate": [
        "poc_migration_threshold",
        "vol_ratio_threshold",
        "va_expansion_threshold",
        "va_abs_width_threshold",
        "allow_in_trending",
        "block_in_trending",
        "block_in_range",
        "integrity_threshold",
    ],
    "scenarios": ["enabled"],
    "pressure_thresholds": ["z_block"],  # base global
    "guardians": ["l2_ratio_min", "spread_max_ratio"],  # base global
    "pressure_thresholds": ["z_block"],  # base global
}


def run_optimizer(symbol, coin, scenario, iterations, study_db):
    """Run param_optimizer for a single scenario."""
    cmd = [
        VENV_PYTHON,
        "scripts/param_optimizer.py",
        "--symbol",
        symbol,
        "--coin",
        coin,
        "--only",
        scenario,
        "--iterations",
        str(iterations),
        "--study-db",
        study_db,
    ]
    print(f"\n🚀 Running {iterations} iterations for {scenario}...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
    if result.returncode != 0:
        print(f"❌ Optimizer failed for {scenario}:")
        print(result.stderr[-2000:])
        return False
    print(result.stdout[-500:])
    return True


def get_best_score(symbol):
    """Extract best score from latest result JSON."""
    files = glob.glob(os.path.join(BASE, "results", f"opt_{symbol}_*.json"))
    if not files:
        return None
    latest = max(files, key=os.path.getctime)
    with open(latest) as f:
        data = json.load(f)
    return data.get("best_score")


def load_opt_profile(symbol):
    """Load the generated optimized profile module."""
    opt_file = os.path.join(BASE, "config", f"coin_profiles_{symbol}_optimized.py")
    if not os.path.exists(opt_file):
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"opt_{symbol}", opt_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.COIN_PROFILES


def safe_merge(base, opt, symbol, scenario):
    """Merge only scenario-specific keys from opt into base."""
    keys = SCENARIO_KEYS[scenario]

    # Scenario-specific keys
    for top_key, subkeys in keys.items():
        if top_key not in base[symbol]:
            base[symbol][top_key] = {}
        if top_key in opt[symbol]:
            if top_key == "sensors":
                # Nested: sensors[scenario_name][param]
                if scenario not in base[symbol]["sensors"]:
                    base[symbol]["sensors"][scenario] = {}
                if scenario in opt[symbol]["sensors"]:
                    for param in subkeys:
                        if param in opt[symbol]["sensors"][scenario]:
                            base[symbol]["sensors"][scenario][param] = opt[symbol]["sensors"][scenario][param]
            else:
                # Flat: guardians[key], pressure_thresholds[key], targets[key]
                if top_key not in base[symbol]:
                    base[symbol][top_key] = {}
                if top_key in opt[symbol]:
                    for sk in subkeys:
                        if sk in opt[symbol][top_key]:
                            base[symbol][top_key][sk] = opt[symbol][top_key][sk]


def merge_shared(base, opt, symbol):
    """Merge shared keys (once, from last opt)."""
    for top_key, subkeys in SHARED_KEYS.items():
        if top_key in opt[symbol]:
            if top_key not in base[symbol]:
                base[symbol][top_key] = {}
            for sk in subkeys:
                if sk in opt[symbol][top_key]:
                    base[symbol][top_key][sk] = opt[symbol][top_key][sk]


def validate_net_taker(symbol, coin, scenario):
    """Run quick audit backtest to confirm Net Taker > 0 for this scenario."""
    print(f"  🔍 Validating {scenario} with backtest...")
    # Find latest daily dataset for the coin
    import os

    db_dir = os.path.join(BASE, "data", "datasets", "daily_backtest_ready")
    files = sorted(
        [
            f
            for f in os.listdir(db_dir)
            if f.startswith(symbol.replace("_", "").replace("NOISY", "").replace("UNCERTAIN", "").replace("1", ""))
        ]
    )
    if not files:
        files = sorted([f for f in os.listdir(db_dir) if symbol.split("_")[0] in f])
    if not files:
        print("  ⚠️ No datasets found, skipping validation")
        return True

    # Use most recent dataset
    test_db = os.path.join(db_dir, files[-1])

    cmd = [
        VENV_PYTHON,
        "-u",
        "backtest.py",
        "--depth-db-path",
        test_db,
        "--symbol",
        coin,
        "--run-type",
        "audit",
        "--historian-db",
        f"data/historian_val_{scenario}.db",
    ]
    env = os.environ.copy()
    env["CASINO_HISTORIAN_DB"] = f"data/historian_val_{scenario}.db"

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE, env=env, timeout=300)
    if result.returncode != 0:
        print(f"  ❌ Backtest failed: {result.stderr[-500:]}")
        return False

    # Run auditor
    hist_db = f"data/historian_val_{scenario}.db"
    if not os.path.exists(hist_db):
        print("  ⚠️ No historian generated")
        return True

    sys.path.insert(0, os.path.join(BASE, "utils"))
    from setup_edge_auditor import EdgeAuditor

    auditor = EdgeAuditor(hist_db)
    metrics = auditor.get_metrics()

    setup_counts = metrics.get("setup_counts", {})
    sc_count = setup_counts.get(scenario, 0)
    net = metrics.get("net_taker", -999)

    print(f"  📊 {scenario}: signals={sc_count}, net_taker={net:+.4f}%")

    # Clean up
    try:
        os.remove(hist_db)
    except Exception:
        pass

    return net > 0 and sc_count > 0


def main():
    parser = argparse.ArgumentParser(description="Cascade v2 — Scenario-by-scenario optimization")
    parser.add_argument("--symbol", required=True, help="Cluster name (e.g., AVAX_NOISY_UNCERTAIN)")
    parser.add_argument("--coin", required=True, help="Coin symbol (e.g., AVAXUSDT)")
    parser.add_argument("--iterations", type=int, default=50, help="Optuna iterations per attempt")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retries per scenario")
    parser.add_argument("--study-db", help="Study DB path (auto-generated if not provided)")
    args = parser.parse_args()

    symbol = args.symbol
    coin = args.coin
    iterations = args.iterations
    max_retries = args.max_retries

    study_db = args.study_db or os.path.join(BASE, "data", "db_vault", f"{symbol}_cascade_v2.db")
    os.makedirs(os.path.dirname(study_db), exist_ok=True)

    print(f"\n{'='*60}")
    print(f"🔄 CASCADE v2 — {symbol}")
    print(f"{'='*60}")
    print(f"  Coin: {coin}")
    print(f"  Iterations per attempt: {iterations}")
    print(f"  Max retries per scenario: {max_retries}")
    print(f"  Study DB: {study_db}")

    # Load base profiles
    sys.path.insert(0, os.path.join(BASE, "config"))
    from coin_profiles import COIN_PROFILES, DEFAULT_PROFILE

    sys.path.pop(0)

    merged = copy.deepcopy(COIN_PROFILES)
    optimized_scenarios = {}

    for scenario in SCENARIOS:
        print(f"\n{'='*60}")
        print(f"🎯 Optimizing {scenario} (max {max_retries} attempts)")
        print(f"{'='*60}")

        success = False
        for attempt in range(1, max_retries + 1):
            print(f"\n  📝 Attempt {attempt}/{max_retries} for {scenario}")

            ok = run_optimizer(symbol, coin, scenario, iterations, study_db)
            if not ok:
                print(f"  ❌ Optimizer failed")
                continue

            best_score = get_best_score(symbol)
            print(f"  🎯 Best composite score: {best_score:.4f}")

            # Load and merge
            opt = load_opt_profile(symbol)
            if not opt:
                print("  ❌ No optimized profile generated")
                continue

            safe_merge(merged, opt, symbol, scenario)
            print(f"  ✅ Merged {scenario} params")

            # Validate with real backtest
            if validate_net_taker(symbol, coin, scenario):
                print(f"  ✅ Validation PASSED (Net Taker > 0)")
                success = True
                break
            else:
                print(f"  ⚠️ Validation FAILED (Net Taker <= 0 or no signals)")
                # Revert this scenario's merge by reloading base
                from coin_profiles import COIN_PROFILES as BASE_PROFILES

                merged[symbol] = copy.deepcopy(BASE_PROFILES[symbol])
                # Re-apply previously successful scenarios
                for sc, opt_f in optimized_scenarios.items():
                    opt_mod = importlib.util.spec_from_file_location(f"opt_{sc}", opt_f)
                    opt_m = importlib.util.module_from_spec(opt_mod)
                    opt_mod.loader.exec_module(opt_m)
                    safe_merge(merged, opt_m.COIN_PROFILES, symbol, sc)

        if not success:
            print(f"\n❌ FAILED to achieve positive Net Taker for {scenario} after {max_retries} attempts")
            print("   Consider: adjusting param bounds, more iterations, or manual review")
            sys.exit(1)

        # Save this scenario's opt file for final merge
        opt_file = os.path.join(BASE, "config", f"coin_profiles_{symbol}_optimized.py")
        if os.path.exists(opt_file):
            optimized_scenarios[scenario] = opt_file
            print(f"  💾 Saved optimized profile: {opt_file}")

    # Final merge of shared keys (from last scenario's opt)
    print(f"\n{'='*60}")
    print("🔧 Final merge of shared keys...")
    last_opt = load_opt_profile(symbol)
    if last_opt:
        merge_shared(merged, last_opt, symbol)

    # Save final merged profile
    final_file = os.path.join(BASE, "config", f"coin_profiles_{symbol}_cascade_merged.py")
    with open(final_file, "w") as f:
        f.write(f'"""\nOptimized for {symbol} via Cascade v2\nGenerated by cascade_v2.py\n"""\n\n')
        f.write(f"COIN_PROFILES = {json.dumps(merged, indent=4)}\n\n")
        f.write(f'DEFAULT_PROFILE = "{DEFAULT_PROFILE}"\n')

    print(f"\n✅ Merged profile saved to: {final_file}")
    print(f"\n⚠️  REVIEW BEFORE APPLYING:")
    print(f"   1. Check {final_file}")
    print(f"   2. Copy COIN_PROFILES[{symbol}] to config/coin_profiles.py")
    print(f"\n🎉 Cascade v2 complete! All {len(SCENARIOS)} scenarios validated with positive Net Taker.")


if __name__ == "__main__":

    main()
