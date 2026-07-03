"""Strategies for the court_homography benchmark.

Unlike benchmarks/suites/court_detection (variants of ONE corner detector, judged by
that detector's own quad scores), these are DIFFERENT algorithms that share
one output contract — a model->image homography + the 30-point keypoint
lattice — so they are all judged by the same mask-support metrics
(line_recall / line_precision / line_f1) from HomographyJudge.

The grid has two axes:
  fitter    : hough_model_fit | projection_1d | keypoint_ransac
  front end : hsv (green-gated white mask, reused from court.detector)
              | tophat (colour-agnostic thin-ridge mask)
plus corners_baseline — the existing 4-corner detector lifted to a
homography — as the reference to beat.
"""

import cv2
import numpy as np

from badminton_analysis.court.detector import auto_detect_court_corners
from badminton_analysis.court_homography import (
    HomographyJudge,
    extraction,
    hough_fit,
    keypoints,
    model,
    projection,
    render_preview,
)

from ...core.types import Sample, Strategy, StrategyOutput

WORK_SIZE = (1080, 720)  # match the pipeline / court_detection default

_FITTERS = {
    "hough_model_fit": hough_fit.detect,
    "projection_1d": projection.detect,
    "keypoint_ransac": keypoints.detect,
}


def _read(sample: Sample):
    if sample.payload is not None:
        return sample.payload
    image = cv2.imread(sample.path)
    if image is None:
        raise FileNotFoundError(f"cannot read image: {sample.path}")
    return cv2.resize(image, WORK_SIZE)


def _finish(name, image, homography, judge, extra_metrics=None):
    """Shared refine + scoring + preview + output packaging for every strategy.

    Every strategy's raw output goes through the same ICP snap-refinement, so
    the benchmark compares the quality of each algorithm's INIT, with an equal
    polishing step on top (judge.refine keeps the original if refining hurts).
    """
    if homography is not None:
        homography = judge.refine(homography)
    scores = judge.score(homography) if homography is not None else {
        "line_recall": 0.0, "line_precision": 0.0, "line_f1": 0.0,
        "in_frame_fraction": 0.0,
    }
    metrics = {"detected": 1.0 if homography is not None else 0.0, **scores}

    info = {"homography": None, "keypoints": None}
    if homography is not None:
        lattice_pts, types, in_frame = model.lattice_in_frame(homography, image.shape)
        metrics["keypoints_in_frame"] = float(in_frame.sum())
        info["homography"] = np.asarray(homography, dtype=float).tolist()
        info["keypoints"] = [
            {"court_xy_m": model.LATTICE_POINTS[i].tolist(),
             "image_xy": lattice_pts[i].tolist(),
             "type": types[i]}
            for i in np.flatnonzero(in_frame)
        ]
    if extra_metrics:
        metrics.update(extra_metrics)

    banner = f"{name}: " + (
        f"f1={scores['line_f1']:.2f} r={scores['line_recall']:.2f} "
        f"p={scores['line_precision']:.2f}"
        if homography is not None else "no detection"
    )
    preview = render_preview(image, homography, banner)
    return StrategyOutput(success=True, metrics=metrics, preview=preview, info=info)


def _debug_metrics(debug):
    return {
        key: float(value)
        for key, value in debug.items()
        if isinstance(value, (int, float, np.integer, np.floating))
    }


def _make(fitter_name, front_end):
    strategy_name = f"{fitter_name}__{front_end}"

    def run(sample: Sample) -> StrategyOutput:
        image = _read(sample)
        judge = HomographyJudge(image)
        segments = extraction.FRONT_ENDS[front_end](image)
        homography, debug = _FITTERS[fitter_name](image, judge, segments=segments)
        return _finish(strategy_name, image, homography, judge, _debug_metrics(debug))

    return run


def _run_corners_baseline(sample: Sample) -> StrategyOutput:
    image = _read(sample)
    judge = HomographyJudge(image)
    corners, _mask, debug = auto_detect_court_corners(image)
    homography = model.homography_from_corners(corners) if corners else None
    extra = {
        "n_horizontal": float(len(debug.get("horizontal") or [])),
        "n_side": float(len(debug.get("side") or [])),
    }
    return _finish("corners_baseline", image, homography, judge, extra)


def _run_ensemble(sample: Sample) -> StrategyOutput:
    """Run the strongest front end per fitter, keep the best-judged fit.

    The three fitters fail on DIFFERENT frames (hough+tophat handles odd
    court colours, projection+hsv nails clean broadcast views, keypoints
    survive partial grids), so per-frame selection by the shared judge
    recovers most of the union at the cost of running all three.
    """
    image = _read(sample)
    judge = HomographyJudge(image)
    attempts = (
        ("hough_model_fit", "tophat"),
        ("projection_1d", "hsv"),
        ("keypoint_ransac", "hsv"),
    )
    best_h, best_f1, best_from = None, -1.0, ""
    for fitter_name, front_end in attempts:
        segments = extraction.FRONT_ENDS[front_end](image)
        homography, _debug = _FITTERS[fitter_name](image, judge, segments=segments)
        if homography is None:
            continue
        f1 = judge.score(homography)["line_f1"]
        if f1 > best_f1:
            best_h, best_f1, best_from = homography, f1, f"{fitter_name}__{front_end}"
    return _finish("ensemble_best", image, best_h, judge,
                   {"picked_" + name: 1.0 if best_from == f"{name}__{fe}" else 0.0
                    for name, fe in attempts})


_DESCRIPTIONS = {
    "hough_model_fit": "Classical model fitting: Hough line pairs assigned to ANY known model lines, best mask-supported homography wins.",
    "projection_1d": "Vanishing-point rectification + 1-D projection histograms matched to model line spacing.",
    "keypoint_ransac": "Keypoint workflow: typed line junctions (L/T/X) matched to the 30-point model lattice, verified by keypoint inliers.",
}
_FRONT_END_NOTES = {
    "hsv": "green-gated HSV mask",
    "tophat": "colour-agnostic top-hat ridge mask",
}

STRATEGIES = {
    "corners_baseline": Strategy(
        name="corners_baseline",
        run=_run_corners_baseline,
        description="Existing 4-corner detector lifted to a homography — the reference to beat.",
    ),
}
for _fitter in _FITTERS:
    for _front in extraction.FRONT_ENDS:
        _name = f"{_fitter}__{_front}"
        STRATEGIES[_name] = Strategy(
            name=_name,
            run=_make(_fitter, _front),
            description=f"{_DESCRIPTIONS[_fitter]} ({_FRONT_END_NOTES[_front]})",
        )

STRATEGIES["ensemble_best"] = Strategy(
    name="ensemble_best",
    run=_run_ensemble,
    description="All three fitters (best front end each); the shared judge picks the winner per frame.",
)
