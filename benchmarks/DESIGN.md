# Benchmark System — Design

Architecture and rationale for the benchmarking framework under `benchmarks/`.
For day-to-day commands see [README.md](./README.md).

## Goals

1. **Compare multiple strategies** of one algorithm on **speed and quality** over a dataset.
2. **Extensible** — new algorithms/workflows plug in without touching the core.
3. **No mandatory labeling** — support quality proxies (self-scores) today, real
   labels later, through the same pipeline.
4. **Easy visual verification** — a self-contained HTML report is the primary artifact.

## Core model

Four concepts, defined in `core/types.py`:

| Concept | Role |
|---------|------|
| **Benchmark** | One algorithm: a dataset loader + the strategies to compare. Registered by name. |
| **Strategy** | A named variant of the algorithm: `run(Sample) -> StrategyOutput`. |
| **Sample** | One input (id + path/payload + meta). |
| **StrategyOutput** | `success`, numeric `metrics`, an optional `preview` image, and non-numeric `info`. |

A run produces one **`RunRecord`** per `(strategy, sample)` pair; the reporter
aggregates records into per-strategy stats.

### Provenance: every run is self-describing

A run directory is named by a sortable timestamp (`YYYYMMDD-HHMMSS`, plus an
optional `--label` suffix) and always contains a **`meta.json` manifest**: the
benchmark, strategy set, data dir, sample count, timestamp, label, and the git
commit that produced it (`-dirty` if the working tree was modified). This is a
hard rule, not a convention — you never have to guess what a results folder was
or whether it can be trusted/reproduced.

### Why "any numeric metric is auto-aggregated"

A strategy just returns a `metrics` dict of numbers. The reporter takes the
union of keys across records and computes count/mean/median/min/max/p95 for each.
This is the key extensibility lever: a new algorithm emits whatever metrics make
sense (accuracy, IoU, F1, latency, memory, counts) and they flow through
aggregation, JSON, and the HTML summary **with zero core changes**.

## Data flow

```
                 ┌────────────────────────── benchmarks/run.py (CLI) ──────────────────────────┐
                 │                                                                              │
  data folder ──▶│  load_samples(dir) ──▶ [Sample, ...]                                         │
                 │                                                                              │
                 │  for strategy in strategies:                                                 │
                 │    for sample in samples:                                                    │
                 │      runner: time strategy.run(sample) ──▶ StrategyOutput                    │
                 │              save preview PNG, capture errors ──▶ RunRecord                   │
                 │                                                                              │
                 │  report.aggregate(records) ──▶ per-strategy stats                            │
                 │  report.write_json / write_html                                              │
                 └──────────────────────────────────────────────────────────────────────────┬─┘
                                                                                              │
   artifacts/results/<benchmark>/<run_id>/  ◀── report · records · summary · meta.json · previews ─┘
```

Module responsibilities:

- `core/dataset.py` — reusable loaders (`load_image_folder`); paths only, so
  strategies control how/when data is read.
- `core/runner.py` — the run loop: timing (with optional `--timing-repeats` to
  report the fastest of N to cut noise/warmup), exception capture, preview saving.
- `core/report.py` — aggregation + JSON + the HTML report.
- `core/registry.py` — name→Benchmark registry; plugins self-register on import.

## The no-labels decision

The court-detection benchmark has no ground-truth corners, so its "quality"
numbers are the **detector's own self-scores** (`score`, `reference_score`,
`horizontal_pattern_score`, `reference_supported_lines`, ...).

- These are valid for **relative** comparison of strategies and for **regression
  detection** (did a change lower scores across the set?).
- They are **not** absolute accuracy — a confidently-wrong detection can score
  high. The per-image preview grid is the real accuracy check.

This caveat is surfaced in three places so it can't be missed: the strategy code,
the HTML report banner, and the READMEs.

**Migration path to labeled accuracy:** when labels exist, add a metric that
compares a strategy's output to the label (e.g. mean corner distance in px, or
homography-projected IoU). Because metrics are auto-aggregated, that new number
appears in `summary.json` and the report automatically. Add it to a benchmark's
`summary_metrics` (and `lower_is_better` if smaller is better) to surface it in
the summary table and highlight the best strategy correctly.

## The report

`report.html` is self-contained (inline CSS, references local preview PNGs) and
has two sections:

1. **Summary table** — one row per strategy; columns are `success %`, each
   `summary_metric` (mean), and latency median/p95. The best cell per column is
   highlighted (max is best, except latency and any metric listed in
   `lower_is_better`).
2. **Per-image comparison** — one block per image, with a horizontal row of
   cards (one per strategy) showing the annotated preview + key metrics, so you
   can eyeball which strategy wins on each image.

## Extending

**New strategy** — add an entry to the algorithm's `STRATEGIES` dict. For court
detection the shared `_detect(image, work_size, preprocess=...)` helper makes
most variants one line.

**New benchmark** — create `benchmarks/suites/<algo>/` with `strategies.py` +
`benchmark.py`; build a `Benchmark(...)`, call `register(BENCHMARK)`, and import
the package in `run.py`. Reuse `core.dataset` loaders or write your own
`load_samples`. Everything else (runner, timing, aggregation, reporting) is
shared. Suites live one level below `benchmarks/`, so relative imports of the
engine use three dots: `from ...core.types import Benchmark`.

## Layout

Three kinds of thing, three roots — they never mix:

```
benchmarks/
├── core/               # ENGINE — algorithm-agnostic (types, registry, dataset, runner, report)
├── suites/             # DEFINITIONS — one subpackage per benchmark ("plugins")
│   ├── court_detection/    #   strategies.py + benchmark.py
│   └── court_homography/    #   strategies.py + benchmark.py + README.md
├── artifacts/          # ARTIFACTS — everything local/generated (gitignored)
│   ├── data/               #   input datasets, one subfolder per benchmark
│   └── results/            #   run outputs: <benchmark>/<run_id>/
├── run.py              # CLI entry point
├── README.md           # usage
└── DESIGN.md           # this document
```

Before this split, benchmark definitions, input data, and output results were
flat siblings under `benchmarks/` — so a folder like `court_detection/` was
ambiguous (definition? results?) and a benchmark couldn't be named `data` or
`results` without colliding. Separating engine / definitions / artifacts removes
that ambiguity and the collision risk.
