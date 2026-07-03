"""Homography-based court detection strategies.

Unlike badminton_analysis.court (which outputs 4 corner points), every
strategy here outputs a full model->image homography plus the projected
30-point court keypoint lattice, following the keypoint/homography workflow
used by modern court detectors. Benchmarked by benchmarks/court_homography.
"""

from . import extraction, hough_fit, keypoints, model, projection
from .render import render_preview
from .scoring import HomographyJudge

__all__ = [
    "model",
    "extraction",
    "hough_fit",
    "projection",
    "keypoints",
    "HomographyJudge",
    "render_preview",
]
