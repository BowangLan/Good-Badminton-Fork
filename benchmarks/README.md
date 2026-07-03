# Benchmarks

A small, extensible framework for benchmarking algorithms/workflows in this repo.
For each algorithm you can define several **strategies** (variants) and compare
their **speed** and **quality** over a dataset, then eyeball the results in a
self-contained HTML report.

## Concepts

| Concept | What it is |
|---------|-----------|
| **Benchmark** | One algorithm + its dataset loader + the strategies to compare. Registered by name. |
| **Strategy** | A named variant of the algorithm (different params, resolution, preprocessing, or a whole different implementation). |
| **Sample** | One input item (e.g. an image). |
| **Metric** | Any number a strategy returns (`score`, `latency_ms`, counts, coverage, a `detected` 0/1 flag). All numeric metrics are aggregated automatically. |

> **On "accuracy" without labels:** the court-detection benchmark has no
> ground-truth corners, so its quality metrics are the algorithm's **own
> self-scores** (confidence proxies). They're great for *comparing strategies*
> and *catching regressions*, but they are **not** absolute accuracy. The
> per-image previews in the report are the real accuracy check. When you later
> add labeled data, add a strategy/metric that compares against labels and it
> will flow through the same aggregation + report unchanged.

## Usage

```bash
# List benchmarks and their strategies
uv run python -m benchmarks.run --list

# Run all strategies on the benchmark's default data dir
uv run python -m benchmarks.run court_detection

# Choose strategies, point at a folder, cap samples
uv run python -m benchmarks.run court_detection \
    --strategies baseline_1080x720,clahe_1080x720 --data templates --limit 20

# Cleaner speed numbers: re-time each run, report the fastest
uv run python -m benchmarks.run court_detection --timing-repeats 3
```

Output lands in `benchmarks/results/<benchmark>/<run_id>/`:

- `report.html` — open in a browser. Summary table (best-in-column highlighted)
  + a per-image grid comparing every strategy side by side.
- `records.json` — every (strategy, sample) run: metrics, latency, corners, errors.
- `summary.json` — per-strategy aggregates (mean/median/p95 of each metric).
- `previews/` — annotated PNGs referenced by the report.

`benchmarks/results/` is gitignored.

## Court detection benchmark

- **Data:** drop images into `benchmarks/data/court_detection/` (or pass
  `--data <folder>`). No labeling needed.
- **Strategies** (`court_detection/strategies.py`): `baseline_1080x720`,
  `lowres_720x480`, `highres_1440x960`, `clahe_1080x720`. Each runs the same
  `auto_detect_court_corners` under different working resolution / preprocessing.
- **Metrics:** `detected`, `score`, `reference_score`, `horizontal_pattern_score`,
  `reference_supported_lines`, segment counts, `latency_ms`.

### Dataset: extract frames from videos

`benchmarks/data/court_detection/` is the default data dir and is **gitignored**
(only `.gitkeep` placeholders are tracked), so datasets are built locally.

`tools/extract_benchmark_frames.py` builds one by sampling random frames from
videos: it selects videos by filename regex and writes N random frames per video
into `set1..setN/` subfolders (one frame per video per set, giving comparable
input sets). Sampling is seeded (reproducible) and drawn from the middle 80% of
each clip to avoid intros/black frames.

Reproduce the current dataset (2 frames each from the `0x_`-named videos):

```bash
uv run python -m tools.extract_benchmark_frames \
    --videos-dir videos --pattern '^0[0-9]_' \
    --out benchmarks/data/court_detection --frames-per-video 2 --seed 42
```

Produces:

```
benchmarks/data/court_detection/
├── set1/   # 9 frames, one per matched video
└── set2/   # 9 frames, one per matched video
```

Then run the benchmark with no `--data` flag (it reads the default dir, recursively):

```bash
uv run python -m benchmarks.run court_detection
```

Options: `--pattern` (filename regex), `--frames-per-video` (number of sets),
`--seed` (change to resample different frames), `--videos-dir`, `--out`.

### Add a new strategy

In `court_detection/strategies.py`, add an entry to `STRATEGIES`. The shared
`_detect(image, work_size, preprocess=...)` helper handles metrics + preview, so
most variants are one line:

```python
"denoise_1080x720": Strategy(
    name="denoise_1080x720",
    run=_make((1080, 720), preprocess=lambda img: cv2.bilateralFilter(img, 7, 50, 50)),
    description="Bilateral denoise before detection.",
),
```

For a genuinely different implementation, write a `run(sample) -> StrategyOutput`
that returns your own `metrics`/`preview`/`info`.

## Add a new benchmark (future algorithms)

1. Create `benchmarks/<my_algo>/` with `strategies.py` and `benchmark.py`.
2. In `benchmark.py`, build a `Benchmark(...)` and call `register(BENCHMARK)`.
   Reuse `core.dataset.load_image_folder` or write your own `load_samples`.
3. Import the package in `benchmarks/run.py` (next to `from . import court_detection`)
   so it self-registers.

The core (`benchmarks/core/`) is algorithm-agnostic: runner, timing,
auto-aggregation of any numeric metric, and the HTML/JSON reporters all work
unchanged for new benchmarks.
