"""Court homography benchmark definition.

Separate from benchmarks/court_detection because the output shape differs:
strategies here return a full model->image homography + keypoint lattice
(not 4 corners), and are judged by shared mask-support metrics rather than
the corner detector's internal quad scores. Reuses the same image dataset.
"""

import os

from ..core.dataset import load_image_folder
from ..core.registry import register
from ..core.types import Benchmark
from .strategies import STRATEGIES

# Same frames as court_detection — the algorithms differ, not the data.
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "court_detection")


def _load(data_dir):
    return load_image_folder(data_dir or DEFAULT_DATA_DIR)


BENCHMARK = Benchmark(
    name="court_homography",
    description=(
        "Homography + keypoint-lattice court detection — compares literature-"
        "inspired strategies (model fitting, 1-D projection, keypoint RANSAC) "
        "against the lifted corner-detector baseline on shared line-support "
        "metrics. Self-scored: line_f1 measures agreement with the white-line "
        "mask, not ground truth."
    ),
    load_samples=_load,
    strategies=STRATEGIES,
    default_data_dir=os.path.normpath(DEFAULT_DATA_DIR),
    summary_metrics=[
        "detected",
        "line_f1",
        "line_recall",
        "line_precision",
        "keypoints_in_frame",
    ],
    lower_is_better=(),
)

register(BENCHMARK)
