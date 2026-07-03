"""Benchmark CLI.

Usage:
    # List available benchmarks and their strategies
    uv run python -m benchmarks.run --list

    # Run all strategies of a benchmark on its default data dir
    uv run python -m benchmarks.run court_detection

    # Pick strategies, point at a data folder, cap sample count
    uv run python -m benchmarks.run court_detection \\
        --strategies baseline_1080x720,clahe_1080x720 --data templates --limit 20

    # Cleaner speed numbers by re-timing each run
    uv run python -m benchmarks.run court_detection --timing-repeats 3

    # Tag a run without breaking the sortable timestamp id
    uv run python -m benchmarks.run court_detection --label court2-vs-baseline

Outputs land in benchmarks/artifacts/results/<benchmark>/<run_id>/
(report.html, records.json, summary.json, meta.json, previews/). The run id is
always a sortable timestamp; --label is recorded in meta.json and appended to
the id for readability.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

# Import benchmark suites so they self-register.
from .suites import court_detection  # noqa: F401
from .suites import court_homography  # noqa: F401
from .core import registry, report
from .core.runner import run_benchmark, select_strategies

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "artifacts", "results")


def _git_commit():
    """Short commit hash of the code that produced this run (or None)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(__file__),
            capture_output=True, text=True, timeout=5,
        )
        rev = out.stdout.strip()
        if out.returncode != 0 or not rev:
            return None
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=os.path.dirname(__file__),
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return rev + ("-dirty" if dirty else "")
    except Exception:
        return None


def _write_manifest(run_dir, *, benchmark, run_id, label, strategies, data_dir,
                    n_samples, timing_repeats, timestamp):
    """Record what produced this run so it can be understood and reproduced."""
    manifest = {
        "benchmark": benchmark,
        "run_id": run_id,
        "label": label,
        "timestamp": timestamp,
        "git_commit": _git_commit(),
        "strategies": [s.name for s in strategies],
        "data_dir": os.path.normpath(data_dir) if data_dir else None,
        "n_samples": n_samples,
        "timing_repeats": timing_repeats,
    }
    with open(os.path.join(run_dir, "meta.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def _print_list():
    print("Available benchmarks:\n")
    for bench in registry.all_benchmarks():
        print(f"  {bench.name} — {bench.description}")
        default = bench.default_data_dir or "(none)"
        print(f"    data dir: {default}")
        for strat in bench.strategies.values():
            print(f"    · {strat.name}: {strat.description}")
        print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("benchmark", nargs="?", help="benchmark name (see --list)")
    parser.add_argument("--list", action="store_true", help="list benchmarks and strategies")
    parser.add_argument("--strategies", default="all", help="comma-separated strategy names, or 'all'")
    parser.add_argument("--data", default=None, help="dataset dir (defaults to the benchmark's default)")
    parser.add_argument("--limit", type=int, default=None, help="max samples to run")
    parser.add_argument("--timing-repeats", type=int, default=1, help="re-time each run N times, report fastest")
    parser.add_argument("--no-previews", action="store_true", help="skip writing preview PNGs")
    parser.add_argument("--label", default=None,
                        help="human tag recorded in meta.json and appended to the timestamp id")
    args = parser.parse_args(argv)

    if args.list or not args.benchmark:
        _print_list()
        return 0

    bench = registry.get(args.benchmark)
    samples = bench.load_samples(args.data)
    if not samples:
        data_dir = args.data or bench.default_data_dir
        print(f"No images found in: {data_dir}")
        print("Add images there (or pass --data <folder>) and re-run.")
        return 1
    if args.limit:
        samples = samples[: args.limit]

    strategy_names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    strategies = select_strategies(bench, strategy_names)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = args.label.strip() if args.label else None
    run_id = f"{timestamp}-{label}" if label else timestamp
    run_dir = os.path.join(RESULTS_ROOT, bench.name, run_id)
    os.makedirs(run_dir, exist_ok=True)

    _write_manifest(
        run_dir,
        benchmark=bench.name,
        run_id=run_id,
        label=label,
        strategies=strategies,
        data_dir=args.data or bench.default_data_dir,
        n_samples=len(samples),
        timing_repeats=args.timing_repeats,
        timestamp=timestamp,
    )

    print(f"Benchmark : {bench.name}")
    print(f"Strategies: {', '.join(s.name for s in strategies)}")
    print(f"Samples   : {len(samples)}")
    print(f"Output    : {run_dir}\n")

    def on_progress(done, total, record):
        status = "ERR" if record.error else ("OK " if record.metrics.get("detected", 1.0) else "no ")
        print(f"  [{done:>3}/{total}] {status} {record.strategy} :: {record.sample_id} "
              f"({record.latency_ms:.0f} ms)")

    records = run_benchmark(
        bench,
        samples,
        strategies,
        run_dir,
        timing_repeats=args.timing_repeats,
        save_previews=not args.no_previews,
        on_progress=on_progress,
    )

    aggregates = report.aggregate(records)
    report.write_json(records, aggregates, run_dir)
    html_path = report.write_html(bench, records, aggregates, run_dir, run_id)

    print("\nDone.")
    print(f"Report: {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
