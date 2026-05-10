#!/usr/bin/env python3
"""
Update memory.md after a workflow runs.
"""

import argparse
import datetime
import pathlib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True, help="Name of the workflow")
    args = parser.parse_args()

    mem_path = pathlib.Path(".agent/memory.md")
    if not mem_path.exists():
        print(f"Warning: {mem_path} does not exist.")
        return

    stamp = datetime.datetime.utcnow().isoformat()
    entry = f"- {stamp} | {args.workflow} | L2 & price ingest completed, CSVs removed.\n"

    with mem_path.open("a") as f:
        f.write(entry)

    print(f"Updated memory.md for workflow: {args.workflow}")


if __name__ == "__main__":
    main()
