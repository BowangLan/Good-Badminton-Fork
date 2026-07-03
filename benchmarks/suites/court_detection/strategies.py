"""Court-detection strategies to benchmark.

Each strategy is a variant of the SAME algorithm (auto_detect_court_corners)
run under different conditions — working resolution, preprocessing, etc. — so we
can compare their speed and self-reported detection quality. Add a new strategy
by writing a `_run(...)`-based function and listing it in STRATEGIES.
"""

import cv2
import numpy as np

from badminton_analysis.court.detector import (
    auto_detect_court_corners,
    render_auto_court_preview,
)
from badminton_analysis.court.mapper import compute_expanded_roi

from ...core.types import Sample, Strategy, StrategyOutput

# Keys pulled out of the detector's debug["details"] into flat metrics.
_DETAIL_KEYS = (
    "reference_score",
    "reference_coverage",
    "reference_supported_lines",
    "horizontal_pattern_score",
    "alignment_score",
    "endpoint_alignment_score",
    "clean_side_support_score",
)


def _read(sample: Sample):
    if sample.payload is not None:
        return sample.payload
    image = cv2.imread(sample.path)
    if image is None:
        raise FileNotFoundError(f"cannot read image: {sample.path}")
    return image


def _detect(image, work_size, preprocess=None):
    """Core shared runner: resize -> optional preprocess -> detect -> metrics + preview."""
    base = cv2.resize(image, work_size)
    if preprocess is not None:
        base = preprocess(base)

    corners, _mask, debug = auto_detect_court_corners(base)
    details = debug.get("details") or {}

    metrics = {
        "detected": 1.0 if corners else 0.0,
        "n_horizontal": float(len(debug.get("horizontal", []))),
        "n_side": float(len(debug.get("side", []))),
        "work_megapixels": round((work_size[0] * work_size[1]) / 1e6, 3),
    }
    if corners:
        metrics["score"] = float(debug.get("score") or 0.0)
        for key in _DETAIL_KEYS:
            if key in details:
                metrics[key] = float(details[key])
        roi = compute_expanded_roi(corners, base.shape)
        preview = render_auto_court_preview(base, corners, roi, debug)
    else:
        preview = render_auto_court_preview(base, None, None, debug)

    return StrategyOutput(
        success=True,
        metrics=metrics,
        preview=preview,
        info={"corners": corners, "work_size": list(work_size)},
    )


def _clahe(image):
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _make(work_size, preprocess=None):
    def run(sample: Sample) -> StrategyOutput:
        return _detect(_read(sample), work_size, preprocess)

    return run


STRATEGIES = {
    "baseline_1080x720": Strategy(
        name="baseline_1080x720",
        run=_make((1080, 720)),
        description="Pipeline default working resolution (mapper.auto_detect_preview).",
    ),
    "lowres_720x480": Strategy(
        name="lowres_720x480",
        run=_make((720, 480)),
        description="Lower resolution — faster, tests robustness to downscaling.",
    ),
    "highres_1440x960": Strategy(
        name="highres_1440x960",
        run=_make((1440, 960)),
        description="Higher resolution — slower, may recover thin/faint lines.",
    ),
    "clahe_1080x720": Strategy(
        name="clahe_1080x720",
        run=_make((1080, 720), preprocess=_clahe),
        description="CLAHE contrast normalization before detection (uneven lighting).",
    ),
}
