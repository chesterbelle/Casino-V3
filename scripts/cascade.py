import glob
import json
import os
import shutil
import subprocess

cluster = "LTC_NOISY_UNCERTAIN_1"
scenarios = ["tactical_absorption", "failed_breakout", "liquidity_exhaustion", "trend_acceptance"]
iterations = 50

for scenario in scenarios:
    while True:
        print("\n==============================================")
        print(f"🚀 Running {iterations} iterations for {scenario}...")
        print("==============================================\n")

        result = subprocess.run(
            [
                "python",
                "scripts/cluster_optimizer.py",
                "--cluster",
                cluster,
                "--only",
                scenario,
                "--iterations",
                str(iterations),
            ]
        )

        if result.returncode != 0:
            print(f"❌ Error running optimization for {scenario}. Exiting.")
            exit(1)

        # Find the latest json result to check the score
        list_of_files = glob.glob(f"results/opt_{cluster}_*.json")
        if not list_of_files:
            print("❌ No results found!")
            exit(1)

        latest_file = max(list_of_files, key=os.path.getctime)

        with open(latest_file, "r") as f:
            data = json.load(f)

        best_score = data.get("best_score", -999)
        print(f"\n🎯 Best score for {scenario}: {best_score}")

        # Copy the optimized profile back to the main config
        opt_file = f"config/coin_profiles_{cluster}_optimized.py"
        if os.path.exists(opt_file):
            shutil.copy(opt_file, "config/coin_profiles.py")
            print(f"✅ Replaced main profile with {opt_file}")

        if best_score > 0:
            print(f"✅ Achieved positive score for {scenario}! Moving to next scenario.")
            break
        else:
            print(
                f"⚠️ Score is still negative ({best_score}). Running another {iterations} iterations for {scenario}..."
            )

print("\n🎉 Cascade optimization complete! All scenarios are positive.")
