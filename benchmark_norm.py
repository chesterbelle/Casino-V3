import os
import sys
import time

# Add root to path for utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.symbol_norm import normalize_symbol  # noqa: E402


def benchmark_normalization(iterations=100000):
    symbol = "BTC/USDT:USDT"
    start = time.time()
    for _ in range(iterations):
        normalize_symbol(symbol)
    end = time.time()
    print(
        f"🚀 Normalization Benchmark: {iterations} iterations in {end-start:.4f}s ({(end-start)/iterations*1e6:.2f}μs per call)"
    )


# Faster version (hypothetical)
_norm_cache = {}


def fast_normalize(symbol: str) -> str:
    if symbol in _norm_cache:
        return _norm_cache[symbol]

    # Minimal logic
    norm = symbol.upper().replace("/", "")
    if ":" in norm:
        norm = norm.split(":")[0]

    _norm_cache[symbol] = norm
    return norm


def benchmark_fast_normalization(iterations=100000):
    symbol = "BTC/USDT:USDT"
    # Warm up cache
    fast_normalize(symbol)

    start = time.time()
    for _ in range(iterations):
        fast_normalize(symbol)
    end = time.time()
    print(
        f"⚡ Fast (Cached) Normalization: {iterations} iterations in {end-start:.4f}s ({(end-start)/iterations*1e6:.2f}μs per call)"
    )


if __name__ == "__main__":
    benchmark_normalization()
    benchmark_fast_normalization()
