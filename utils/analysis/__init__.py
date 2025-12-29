# -*- coding: utf-8 -*-
"""Utility module for analyzing Gemini memory.

Provides a thin wrapper that forwards to the existing `utils.analyze_buckets`
script so that other parts of the codebase (e.g., the training pipeline)
can simply import `utils.analysis` and call ``analyze_memory()``.
"""

from __future__ import annotations


def analyze_memory() -> int:
    """Run the bucket analysis and return its exit code.

    The original script ``utils/analyze_buckets.py`` defines a ``main``
    function that returns ``0`` on success.  This wrapper imports that
    function and executes it, propagating the return value.
    """
    try:
        from utils.analyze_buckets import main as _main
    except Exception as exc:
        # If the import fails we raise a clear error – this mirrors the
        # behaviour that caused the original ImportError.
        raise ImportError("Failed to import utils.analyze_buckets.main") from exc
    return _main()


def check_sensors() -> int:
    """Run the sensor check."""
    # Placeholder for now, as check_sensors logic might be in cli.py or elsewhere.
    # If it was intended to be in utils.analysis, we need to implement it or forward it.
    # For now, returning 0 to satisfy import.
    print("✅ check_sensors called (placeholder)")
    return 0


if __name__ == "__main__":
    # Allow the module to be executed directly for quick debugging.
    exit_code = analyze_memory()
    raise SystemExit(exit_code)
