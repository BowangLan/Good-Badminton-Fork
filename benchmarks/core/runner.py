"""Executes strategies over samples and produces RunRecords."""

import os
import time
import traceback

from .types import Benchmark, RunRecord


def _save_preview(preview, run_dir, strategy_name, sample_id):
    if preview is None:
        return None
    # Imported lazily so the framework has no hard cv2 dependency.
    import cv2

    previews_dir = os.path.join(run_dir, "previews")
    os.makedirs(previews_dir, exist_ok=True)
    filename = f"{strategy_name}__{sample_id}.png"
    abs_path = os.path.join(previews_dir, filename)
    cv2.imwrite(abs_path, preview)
    return os.path.join("previews", filename)  # relative to run_dir


def select_strategies(benchmark: Benchmark, names):
    if not names or names == ["all"]:
        return list(benchmark.strategies.values())
    chosen = []
    for name in names:
        if name not in benchmark.strategies:
            available = ", ".join(benchmark.strategies)
            raise KeyError(f"unknown strategy '{name}' for {benchmark.name}. Available: {available}")
        chosen.append(benchmark.strategies[name])
    return chosen


def run_benchmark(
    benchmark: Benchmark,
    samples,
    strategies,
    run_dir,
    timing_repeats=1,
    save_previews=True,
    on_progress=None,
):
    """Run every (strategy, sample) pair.

    timing_repeats: run each strategy N times per sample; the fastest run's
        latency is reported (metrics/preview come from the first run). Use >1 to
        get cleaner speed numbers with less noise / warmup bias.
    """
    records = []
    total = len(strategies) * len(samples)
    done = 0

    for strategy in strategies:
        for sample in samples:
            best_latency = None
            output = None
            error = None
            for attempt in range(max(1, timing_repeats)):
                start = time.perf_counter()
                try:
                    result = strategy.run(sample)
                    elapsed = (time.perf_counter() - start) * 1000.0
                except Exception:
                    elapsed = (time.perf_counter() - start) * 1000.0
                    error = traceback.format_exc()
                    result = None
                if best_latency is None or elapsed < best_latency:
                    best_latency = elapsed
                if attempt == 0:
                    output = result
                if error is not None:
                    break

            if error is not None or output is None:
                record = RunRecord(
                    benchmark=benchmark.name,
                    strategy=strategy.name,
                    sample_id=sample.id,
                    success=False,
                    latency_ms=best_latency or 0.0,
                    error=error or "strategy returned None",
                )
            else:
                preview_path = None
                if save_previews:
                    preview_path = _save_preview(output.preview, run_dir, strategy.name, sample.id)
                record = RunRecord(
                    benchmark=benchmark.name,
                    strategy=strategy.name,
                    sample_id=sample.id,
                    success=bool(output.success),
                    latency_ms=best_latency or 0.0,
                    metrics=dict(output.metrics),
                    info=dict(output.info),
                    preview_path=preview_path,
                )

            records.append(record)
            done += 1
            if on_progress:
                on_progress(done, total, record)

    return records
