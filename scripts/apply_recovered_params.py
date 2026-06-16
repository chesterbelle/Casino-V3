import copy
import json
import os
import sys

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_BASE, "config"))
from coin_profiles import COIN_PROFILES, DEFAULT_PROFILE  # noqa: E402


def apply():
    pass


with open(os.path.join(_BASE, "results", "recovered_opt_THIN_VOLATILE.json"), "r") as f:
    recovered = json.load(f)

best_params = recovered["best_params"]
cluster = "THIN_VOLATILE"

profile = copy.deepcopy(COIN_PROFILES[cluster])
for key, value in best_params.items():
    parts = key.split(".")
    d = profile
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value

modified_profiles = copy.deepcopy(COIN_PROFILES)
modified_profiles[cluster] = profile

output_path = os.path.join(_BASE, "config", "coin_profiles_THIN_VOLATILE_final.py")
with open(output_path, "w") as f:
    f.write(f'"""Optimized for {cluster} - Recovered from DB"""\n\n')
    f.write(f"COIN_PROFILES = {json.dumps(modified_profiles, indent=4)}\n\n")
    f.write(f'DEFAULT_PROFILE = "{DEFAULT_PROFILE}"\n')

print(f"Final profile saved to {output_path}")

if __name__ == "__main__":
    apply()
