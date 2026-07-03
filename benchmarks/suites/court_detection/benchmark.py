"""Court line detection benchmark definition."""

import os

from ...core.dataset import load_image_folder
from ...core.registry import register
from ...core.types import Benchmark
from .strategies import STRATEGIES

# Default dataset location — drop your benchmark images here (prepared separately).
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "data", "court_detection")


def _load(data_dir):
    return load_image_folder(data_dir or DEFAULT_DATA_DIR)


BENCHMARK = Benchmark(
    name="court_detection",
    description="Auto court-corner detection — compares detection strategies on a folder of images.",
    load_samples=_load,
    strategies=STRATEGIES,
    default_data_dir=os.path.normpath(DEFAULT_DATA_DIR),
    # Order shown in the summary table + used as per-card key metrics.
    summary_metrics=[
        "detected",
        "score",
        "reference_score",
        "horizontal_pattern_score",
        "reference_supported_lines",
    ],
    lower_is_better=(),
)

register(BENCHMARK)
