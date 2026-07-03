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

Outputs land in benchmarks/results/<benchmark>/<run_id>/ (report.html, records.json, summary.json, previews/).
"""

import argparse
import os
import sys
from datetime import datetime

# Import benchmark plugins so they self-register.
from . import court_detection  # noqa: F401
from .core import registry, report
from .core.runner import run_benchmark, select_strategies

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "results")


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
    parser.add_argument("--run-id", default=None, help="override run id (default: timestamp)")
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

    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(RESULTS_ROOT, bench.name, run_id)
    os.makedirs(run_dir, exist_ok=True)

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
