"""Registry of available benchmarks.

Each benchmark plugin registers itself at import time by calling `register()`.
`run.py` imports the known plugin modules so they populate this registry.
"""

from .types import Benchmark

_BENCHMARKS: dict = {}


def register(benchmark: Benchmark) -> Benchmark:
    if benchmark.name in _BENCHMARKS:
        raise ValueError(f"benchmark already registered: {benchmark.name}")
    _BENCHMARKS[benchmark.name] = benchmark
    return benchmark


def get(name: str) -> Benchmark:
    if name not in _BENCHMARKS:
        available = ", ".join(sorted(_BENCHMARKS)) or "(none)"
        raise KeyError(f"unknown benchmark '{name}'. Available: {available}")
    return _BENCHMARKS[name]


def all_names() -> list:
    return sorted(_BENCHMARKS)


def all_benchmarks() -> list:
    return [_BENCHMARKS[name] for name in all_names()]
