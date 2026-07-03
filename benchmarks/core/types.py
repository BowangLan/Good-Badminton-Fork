"""Shared data types for the benchmarking framework.

These are intentionally algorithm-agnostic. A benchmark plugin (e.g. court
detection) turns raw inputs into `Sample`s and provides `Strategy`s that map a
`Sample` to a `StrategyOutput`. The runner produces `RunRecord`s, which the
reporter aggregates.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Sample:
    """One benchmark input (e.g. one image)."""

    id: str
    path: Optional[str] = None          # source file on disk, if any
    payload: Any = None                 # optional pre-loaded data (lazy loaders may leave this None)
    meta: dict = field(default_factory=dict)


@dataclass
class StrategyOutput:
    """What a strategy returns for a single sample.

    metrics : numeric values that get aggregated automatically (score, counts,
              coverage, a `detected` 0/1 flag, ...). Only include numbers here.
    preview : optional BGR numpy image saved to disk for visual inspection.
    info    : non-numeric details kept in the record (corners, notes, ...).
    """

    success: bool = True
    metrics: dict = field(default_factory=dict)
    preview: Any = None
    info: dict = field(default_factory=dict)


@dataclass
class Strategy:
    """A named variant of an algorithm to benchmark."""

    name: str
    run: Callable[[Sample], StrategyOutput]
    description: str = ""


@dataclass
class Benchmark:
    """A complete benchmark: a dataset loader plus the strategies to compare."""

    name: str
    load_samples: Callable[[Optional[str]], list]   # (data_dir) -> list[Sample]
    strategies: dict                                # name -> Strategy
    description: str = ""
    default_data_dir: Optional[str] = None
    # Metrics surfaced in the summary table (in order). None => every numeric metric.
    summary_metrics: Optional[list] = None
    # Metrics where SMALLER is better (rendered/highlighted accordingly).
    lower_is_better: tuple = ()


@dataclass
class RunRecord:
    """The result of running one strategy on one sample."""

    benchmark: str
    strategy: str
    sample_id: str
    success: bool
    latency_ms: float
    metrics: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)
    preview_path: Optional[str] = None   # relative to the run directory
    error: Optional[str] = None

    def to_dict(self):
        return {
            "benchmark": self.benchmark,
            "strategy": self.strategy,
            "sample_id": self.sample_id,
            "success": self.success,
            "latency_ms": round(self.latency_ms, 3),
            "metrics": self.metrics,
            "info": self.info,
            "preview_path": self.preview_path,
            "error": self.error,
        }
