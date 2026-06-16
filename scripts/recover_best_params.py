import json
import os

import optuna

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDY_DB = os.path.join(_BASE, "results", "study_THIN_VOLATILE.db")
OUTPUT_JSON = os.path.join(_BASE, "results", "recovered_opt_THIN_VOLATILE.json")


def recover():
    storage = f"sqlite:///{STUDY_DB}"
    study = optuna.load_study(study_name="THIN_VOLATILE", storage=storage)

    print(f"Best Value: {study.best_value}")
    print(f"Best Params: {json.dumps(study.best_params, indent=4)}")

    with open(OUTPUT_JSON, "w") as f:
        json.dump(
            {"best_value": study.best_value, "best_params": study.best_params, "status": "recovered_from_db"},
            f,
            indent=2,
        )
    print(f"Results saved to {OUTPUT_JSON}")


if __name__ == "__main__":
    recover()
