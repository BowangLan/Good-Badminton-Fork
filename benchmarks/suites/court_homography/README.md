# Court homography benchmark

Compares literature-inspired court-detection strategies that output a **full
model→image homography + the 30-point court keypoint lattice**, instead of the
4 corner points the original detector returns. Separate from
`benchmarks/suites/court_detection` because the output shape — and therefore the
judging — is different; it reuses the same image dataset
(`benchmarks/artifacts/data/court_detection/`).

```bash
uv run python -m benchmarks.run court_homography
uv run python -m benchmarks.run court_homography --strategies ensemble_best
```

## Background

Court detection in the literature falls into two generations:

- **Classical geometry pipelines** — white-pixel/edge extraction → line
  candidates (usually Hough-transform voting) → fit against the known court
  geometry. A 2023 refinement replaces line-parameter voting with **1-D
  projection histograms**: after removing perspective, each line family
  collapses onto one axis and line positions become histogram peaks matched
  against the known court spacing.
- **Deep-learning keypoint methods** (Court R-CNN, CourtKeyNet) — predict
  court keypoints (corners + line intersections), enforce geometric
  consistency (the court is a known planar target), then compute the
  homography. Downstream, the homography feeds player tracking, in/out calls,
  and tactical analysis.

The strategies here implement both classical pipelines and a training-free
stand-in for the keypoint workflow with the same output contract, so a learned
keypoint model can later drop into the same slot and be judged identically.

## Architecture

Detection code lives in `badminton_analysis/court_homography/`:

| Module | Role |
|--------|------|
| `model.py` | BWF-spec metric court model: painted segments, 30-point keypoint lattice with junction types (L/T/X), projection helpers, plausibility gates. |
| `extraction.py` | Two line-pixel front ends: `hsv` (green-gated mask reused from `court.detector`) and `tophat` (colour-agnostic thin-ridge mask — survives bright/pale/pink arenas where the HSV white threshold floods). |
| `hough_fit.py` | Classical model fitting: pairs of detected lines are assigned to **any** plausible model lines (not just the outer boundary), each hypothesis scored by mask support. |
| `projection.py` | 1-D projection: robust vanishing points → rectification → per-axis anisotropic canvas → histogram peaks matched to model line spacing (spacing ratios are exact under the affine ambiguity). |
| `keypoints.py` | Keypoint workflow: typed line junctions → junction grid quads → type-constrained lattice assignments → keypoint-inlier verification → least-squares refit. |
| `scoring.py` | `HomographyJudge`: shared no-labels quality judge + ICP snap-refinement. |
| `render.py` | Preview rendering (projected model + lattice keypoints). |

Every strategy's raw output goes through the same `judge.refine()` polish, so
the benchmark compares init quality on equal footing.

## Judging (no labels)

All strategies are scored by mask support, computed identically:

- `line_recall` — fraction of densely projected model-line samples (in-frame
  only) landing near a white-line pixel. Dense per-line sampling matters:
  endpoint-only projection hides mid-line drift and explodes near the horizon.
- `line_precision` — fraction of line-mask pixels **inside the projected court
  hull** near a projected line. Restricting the denominator to the hull keeps
  off-court clutter from capping the score.
- `line_f1` — the headline number.

These are self-scores: valid for comparing strategies and catching
regressions, not absolute accuracy. Empirically on this dataset **f1 ≥ 0.6 has
matched a visually correct fit; 0.5–0.6 is borderline and can be a confident
wrong fit on pathological frames** (e.g. extreme close-ups where little court
is visible). The preview grid in `report.html` is the real accuracy check.

## Strategies & results

14 frames (level1 = clean broadcast, level2 = half-court/odd views, level3 =
extreme close-up/steep angle), 1080×720 work size:

| strategy | detected | mean f1 | median latency |
|----------|---------:|--------:|---------------:|
| corners_baseline (existing detector) | 7/14 | 0.34 | ~110 ms |
| hough_model_fit__hsv | 9/14 | 0.47 | ~320 ms |
| **hough_model_fit__tophat** | **11/14** | **0.62** | ~580 ms |
| projection_1d__hsv | 9/14 | 0.51 | ~105 ms |
| projection_1d__tophat | 9/14 | 0.40 | ~105 ms |
| keypoint_ransac__hsv | 8/14 | 0.41 | ~90 ms |
| keypoint_ransac__tophat | 8/14 | 0.39 | ~70 ms |
| **ensemble_best** | **13/14** | **0.76** | ~700 ms |

Reading the grid:

- The **front end matters as much as the fitter**: `tophat` rescues frames
  whose court colour breaks the green-gated mask (both Lee Chong Wei frames,
  Taufik/London-pink arena) but adds clutter peaks that hurt `projection_1d`;
  `hsv` gives cleaner profiles where it works at all.
- The fitters fail on **different** frames, so `ensemble_best` (each fitter on
  its best front end, shared judge picks per frame) recovers most of the
  union: 13/14 at mean f1 0.76.
- The one remaining failure (level3 Lee Zii Jia) shows almost no court; the
  level3 Chen Long "detection" at f1 0.57 is a wrong fit — see the caveat
  above about the 0.5–0.6 band.

## Extending

- **New fitter**: implement `detect(image, judge, segments=None) ->
  (homography|None, debug)` in `badminton_analysis/court_homography/`, add it
  to `_FITTERS` in `strategies.py` — it gets both front ends for free.
- **Learned keypoints**: predict lattice keypoints with a CNN, then reuse
  `model.LATTICE_POINTS` + `cv2.findHomography` + the same judge — the
  `keypoint_ransac` strategy shows the exact output contract.
- **Labeled accuracy**: when ground-truth homographies/corners exist, add IoU
  or mean keypoint error next to the self-scores; the framework aggregates any
  numeric metric automatically.
