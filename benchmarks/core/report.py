"""Aggregation + JSON/HTML reporting for benchmark runs."""

import html
import json
import os
from collections import OrderedDict

LATENCY_KEY = "latency_ms"


def _stats(values):
    if not values:
        return None
    import numpy as np

    arr = np.asarray(values, dtype=float)
    return {
        "count": int(arr.size),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "p95": float(np.percentile(arr, 95)),
    }


def aggregate(records):
    """Aggregate records into per-strategy stats.

    Returns an ordered dict: strategy -> {runs, success, errors, success_rate,
    latency: stats, metrics: {key: stats}}. Every numeric metric present on any
    successful run is aggregated over the runs where it appears.
    """
    by_strategy = OrderedDict()
    for record in records:
        by_strategy.setdefault(record.strategy, []).append(record)

    aggregates = OrderedDict()
    for strategy, recs in by_strategy.items():
        ok = [r for r in recs if r.success]
        errors = [r for r in recs if r.error]

        metric_values = {}
        for r in ok:
            for key, value in r.metrics.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                metric_values.setdefault(key, []).append(float(value))

        aggregates[strategy] = {
            "runs": len(recs),
            "success": len(ok),
            "errors": len(errors),
            "success_rate": (len(ok) / len(recs)) if recs else 0.0,
            "latency": _stats([r.latency_ms for r in recs]),
            "metrics": {key: _stats(vals) for key, vals in sorted(metric_values.items())},
        }
    return aggregates


def _metric_columns(benchmark, aggregates):
    if benchmark.summary_metrics is not None:
        return list(benchmark.summary_metrics)
    keys = []
    for agg in aggregates.values():
        for key in agg["metrics"]:
            if key not in keys:
                keys.append(key)
    return keys


def write_json(records, aggregates, run_dir):
    with open(os.path.join(run_dir, "records.json"), "w") as f:
        json.dump([r.to_dict() for r in records], f, indent=2)
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(aggregates, f, indent=2)


# --------------------------------------------------------------------------- HTML

_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; background: #0f1115; color: #e6e6e6;
       font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 32px 0 12px; border-bottom: 1px solid #2a2f3a; padding-bottom: 6px; }
.meta { color: #8a93a3; font-size: 13px; margin-bottom: 8px; }
.note { color: #c8a24a; background: #241f12; border: 1px solid #4a3f1f; border-radius: 8px;
        padding: 10px 14px; margin: 12px 0; font-size: 13px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 7px 12px; text-align: right; border-bottom: 1px solid #232833; white-space: nowrap; }
th { color: #9aa4b5; font-weight: 600; position: sticky; top: 0; background: #0f1115; }
td.name, th.name { text-align: left; font-weight: 600; }
tr:hover td { background: #171b22; }
td.best { color: #5ad17f; font-weight: 700; }
.grid-sample { margin: 22px 0; }
.grid-sample > .label { color: #cfd6e2; font-weight: 600; margin-bottom: 8px; word-break: break-all; }
.cards { display: flex; gap: 14px; overflow-x: auto; padding-bottom: 8px; }
.card { flex: 0 0 300px; background: #161a21; border: 1px solid #262c37; border-radius: 10px;
        overflow: hidden; }
.card img { width: 100%; display: block; background: #000; }
.card .body { padding: 8px 10px; }
.card .strat { font-weight: 600; margin-bottom: 4px; }
.badge { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 10px; margin-left: 6px; }
.badge.ok { background: #14351f; color: #5ad17f; }
.badge.no { background: #3a1a1a; color: #e06767; }
.kv { color: #9aa4b5; font-size: 12px; }
.kv b { color: #e6e6e6; font-weight: 600; }
a { color: inherit; text-decoration: none; }
.card img { cursor: zoom-in; }
.card .newtab { display: block; padding: 4px 10px 8px; font-size: 11px; color: #7f8ba0; }
.card .newtab:hover { color: #cfd6e2; }
/* lightbox */
#lightbox { position: fixed; inset: 0; z-index: 1000; display: none;
            background: rgba(0,0,0,.92); cursor: zoom-out; }
#lightbox.open { display: flex; flex-direction: column; }
#lightbox .lb-bar { flex: 0 0 auto; display: flex; justify-content: space-between;
                    align-items: center; padding: 10px 16px; color: #cfd6e2; font-size: 13px; gap: 12px; }
#lightbox .lb-bar a { color: #8ab4ff; }
#lightbox .lb-stage { flex: 1 1 auto; display: flex; align-items: center;
                      justify-content: center; overflow: auto; padding: 0 16px 16px; }
#lightbox img { max-width: 100%; max-height: 100%; object-fit: contain; cursor: default; }
#lightbox .lb-close { cursor: pointer; font-size: 20px; line-height: 1; color: #cfd6e2; }
"""

_LIGHTBOX_JS = """
(function () {
  var lb = document.getElementById('lightbox');
  var img = document.getElementById('lb-img');
  var cap = document.getElementById('lb-cap');
  var link = document.getElementById('lb-link');
  function open(src, caption) {
    img.src = src; cap.textContent = caption || ''; link.href = src;
    lb.classList.add('open');
  }
  function close() { lb.classList.remove('open'); img.src = ''; }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-full]');
    if (t) { e.preventDefault(); open(t.getAttribute('data-full'), t.getAttribute('data-cap')); }
  });
  lb.addEventListener('click', function (e) {
    if (e.target === lb || e.target.classList.contains('lb-stage') || e.target.classList.contains('lb-close')) close();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
})();
"""

_LIGHTBOX_HTML = (
    '<div id="lightbox"><div class="lb-bar">'
    '<span id="lb-cap"></span>'
    '<span><a id="lb-link" target="_blank">open in new tab ↗</a>'
    ' &nbsp; <span class="lb-close" title="close (Esc)">✕</span></span>'
    '</div><div class="lb-stage"><img id="lb-img" alt=""></div></div>'
)


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        if abs(value) >= 1000 or (value != 0 and abs(value) < 0.01):
            return f"{value:.2f}"
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _best_index(values, lower_is_better):
    nums = [(i, v) for i, v in enumerate(values) if v is not None]
    if not nums:
        return None
    return (min if lower_is_better else max)(nums, key=lambda pair: pair[1])[0]


def _summary_table(benchmark, aggregates):
    strategies = list(aggregates)
    metric_cols = _metric_columns(benchmark, aggregates)
    lower = set(benchmark.lower_is_better)

    # column -> per-strategy value (mean for metrics)
    columns = OrderedDict()
    columns["success %"] = [aggregates[s]["success_rate"] * 100 for s in strategies]
    for key in metric_cols:
        columns[key] = [
            (aggregates[s]["metrics"].get(key) or {}).get("mean") for s in strategies
        ]
    columns["lat median (ms)"] = [
        (aggregates[s]["latency"] or {}).get("median") for s in strategies
    ]
    columns["lat p95 (ms)"] = [
        (aggregates[s]["latency"] or {}).get("p95") for s in strategies
    ]

    lower_cols = {"lat median (ms)", "lat p95 (ms)"} | lower
    best = {col: _best_index(vals, col in lower_cols) for col, vals in columns.items()}

    head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    rows = []
    for i, strat in enumerate(strategies):
        cells = [f'<td class="name">{html.escape(strat)}</td>',
                 f'<td>{aggregates[strat]["runs"]}</td>']
        for col, vals in columns.items():
            cls = "best" if best[col] == i else ""
            cells.append(f'<td class="{cls}">{_fmt(vals[i])}</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")

    return (
        '<div class="scroll"><table>'
        f'<thead><tr><th class="name">strategy</th><th>runs</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _sample_grid(benchmark, records):
    # preserve first-seen sample order and strategy order
    sample_order = []
    strat_order = []
    lookup = {}
    for r in records:
        if r.sample_id not in sample_order:
            sample_order.append(r.sample_id)
        if r.strategy not in strat_order:
            strat_order.append(r.strategy)
        lookup[(r.strategy, r.sample_id)] = r

    key_metrics = benchmark.summary_metrics or []
    blocks = []
    for sample_id in sample_order:
        cards = []
        for strat in strat_order:
            r = lookup.get((strat, sample_id))
            if r is None:
                continue
            if r.error:
                badge = '<span class="badge no">error</span>'
            elif r.metrics.get("detected", 1.0):
                badge = '<span class="badge ok">detected</span>'
            else:
                badge = '<span class="badge no">no court</span>'

            if r.preview_path:
                src = html.escape(r.preview_path)
                cap = html.escape(f"{strat} · {sample_id}")
                img = (f'<img loading="lazy" src="{src}" data-full="{src}" data-cap="{cap}" '
                       f'title="click to view full size">'
                       f'<a class="newtab" href="{src}" target="_blank">open in new tab ↗</a>')
            else:
                img = ""

            kvs = [f'<span class="kv">lat <b>{_fmt(r.latency_ms)}</b>ms</span>']
            for key in key_metrics:
                if key in r.metrics:
                    kvs.append(f'<span class="kv">{html.escape(key)} <b>{_fmt(r.metrics[key])}</b></span>')
            body = (f'<div class="strat">{html.escape(strat)}{badge}</div>'
                    + " · ".join(kvs))
            cards.append(f'<div class="card">{img}<div class="body">{body}</div></div>')

        blocks.append(
            f'<div class="grid-sample"><div class="label">{html.escape(sample_id)}</div>'
            f'<div class="cards">{"".join(cards)}</div></div>'
        )
    return "".join(blocks)


def write_html(benchmark, records, aggregates, run_dir, run_id):
    n_samples = len({r.sample_id for r in records})
    n_strats = len({r.strategy for r in records})
    body = [
        f"<h1>Benchmark: {html.escape(benchmark.name)}</h1>",
        f'<div class="meta">run {html.escape(run_id)} · {n_strats} strategies '
        f"× {n_samples} samples · {len(records)} runs</div>",
        '<div class="note">No ground-truth labels: the quality metrics below are the '
        "algorithm's own self-scores (confidence proxies), useful for comparing "
        "strategies and catching regressions — <b>not</b> absolute accuracy. Use the "
        "per-image previews for the real accuracy check.</div>",
        "<h2>Summary</h2>",
        _summary_table(benchmark, aggregates),
        "<h2>Per-image comparison</h2>",
        _sample_grid(benchmark, records),
    ]
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>benchmark: {html.escape(benchmark.name)}</title>"
        f"<style>{_CSS}</style></head><body>{''.join(body)}"
        f"{_LIGHTBOX_HTML}<script>{_LIGHTBOX_JS}</script></body></html>"
    )
    path = os.path.join(run_dir, "report.html")
    with open(path, "w") as f:
        f.write(doc)
    return path
