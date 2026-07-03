"""Homography quality scoring against the white court-line mask.

Every strategy in this package outputs a model->image homography, so they can
all be judged the same way, with no labels required:

- recall    : fraction of densely projected model-line samples (in-frame only)
              that land on/near a white line pixel. Dense per-line sampling
              matters — projecting only endpoints hides mid-line drift and
              explodes near the horizon.
- precision : fraction of white line pixels INSIDE the projected court hull
              that are near a projected model line. Restricting the
              denominator to the hull keeps off-court clutter (ad boards,
              crowd) from capping the score.
- f1        : harmonic mean; the headline self-score.

These are self-scores (the mask itself can be wrong), valid for comparing
strategies and catching regressions — not absolute accuracy.
"""

import cv2
import numpy as np

from . import model
from .extraction import tophat_line_mask


class HomographyJudge:
    """Precomputes the line mask + distance transform for one image so many
    candidate homographies can be scored cheaply.

    The default mask is the colour-agnostic top-hat line mask — thin bright
    pixels only — so scores stay meaningful on bright/pale courts where the
    HSV white threshold floods.
    """

    def __init__(self, image, line_mask=None):
        self.shape = image.shape[:2]
        height, width = self.shape
        mask = line_mask if line_mask is not None else tophat_line_mask(image)
        self.mask = (mask > 0).astype(np.uint8)
        self.distance_map, labels = cv2.distanceTransformWithLabels(
            1 - self.mask, cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL
        )
        # labels -> coordinates of the nearest line pixel, for snapping.
        line_ys, line_xs = np.nonzero(self.mask)
        if len(line_xs):
            lut = np.zeros((int(labels.max()) + 1, 2), dtype=np.float32)
            lut[labels[line_ys, line_xs]] = np.column_stack([line_xs, line_ys])
            self._nearest_xy = lut[labels]  # H x W x 2
        else:
            self._nearest_xy = None
        self.tolerance = max(4.0, min(width, height) * 0.011)
        self._dense_pts, self._dense_ids = model.dense_line_samples(step_m=0.05)
        self._coarse_pts, _ = model.dense_line_samples(step_m=0.35)

    def _in_frame(self, pts, valid):
        height, width = self.shape
        return (
            valid
            & (pts[:, 0] >= 0)
            & (pts[:, 0] <= width - 1)
            & (pts[:, 1] >= 0)
            & (pts[:, 1] <= height - 1)
        )

    def _recall(self, homography, points_m):
        pts, valid = model.project_points(homography, points_m)
        keep = self._in_frame(pts, valid)
        if keep.sum() < max(8, 0.15 * len(points_m)):
            return 0.0, keep
        xs = np.rint(pts[keep, 0]).astype(np.int32)
        ys = np.rint(pts[keep, 1]).astype(np.int32)
        distances = self.distance_map[ys, xs]
        return float(np.mean(distances <= self.tolerance)), keep

    def quick_score(self, homography):
        """Cheap triage score: recall on a coarse sampling only."""
        recall, _keep = self._recall(homography, self._coarse_pts)
        return recall

    def refine(self, homography, iterations=4, step_m=0.10):
        """ICP-style refinement: snap densely projected model points to their
        nearest line pixel and re-estimate the homography (robustly), a few
        rounds. Returns the refined homography only if it doesn't score worse;
        callers can pass any strategy's output through this unchanged.
        """
        if homography is None or self._nearest_xy is None:
            return homography
        points_m, _ids = model.dense_line_samples(step_m=step_m)
        snap_radius = 3.0 * self.tolerance
        current = np.asarray(homography, dtype=np.float64)
        for _ in range(iterations):
            pts, valid = model.project_points(current, points_m)
            keep = self._in_frame(pts, valid)
            if keep.sum() < 40:
                return homography
            xs = np.rint(pts[keep, 0]).astype(np.int32)
            ys = np.rint(pts[keep, 1]).astype(np.int32)
            near = self.distance_map[ys, xs] <= snap_radius
            if near.sum() < 40:
                return homography
            source = points_m[keep][near]
            target = self._nearest_xy[ys[near], xs[near]]
            refined, _inliers = cv2.findHomography(
                source.reshape(-1, 1, 2),
                target.reshape(-1, 1, 2),
                cv2.RANSAC,
                max(2.0, self.tolerance * 0.6),
            )
            if refined is None or not model.full_court_plausible(refined, (self.shape[0], self.shape[1])):
                break
            current = refined
        if self.score(current)["line_f1"] >= self.score(homography)["line_f1"]:
            return current
        return homography

    def score(self, homography):
        """Full recall / precision / f1 for one homography."""
        empty = {"line_recall": 0.0, "line_precision": 0.0, "line_f1": 0.0,
                 "in_frame_fraction": 0.0}
        if homography is None:
            return empty

        recall, keep = self._recall(homography, self._dense_pts)
        in_frame_fraction = float(np.mean(keep))
        if recall == 0.0:
            empty["in_frame_fraction"] = round(in_frame_fraction, 4)
            return empty

        height, width = self.shape
        pts, _valid = model.project_points(homography, self._dense_pts)

        # Rendered court: draw consecutive in-frame samples of the same line.
        canvas = np.zeros(self.shape, dtype=np.uint8)
        thickness = max(2, int(round(self.tolerance)))
        same_line = self._dense_ids[:-1] == self._dense_ids[1:]
        drawable = same_line & keep[:-1] & keep[1:]
        p = np.rint(pts).astype(np.int32)
        for idx in np.flatnonzero(drawable):
            cv2.line(canvas, tuple(p[idx]), tuple(p[idx + 1]), 1, thickness)

        # Court hull: projected outer corners clipped to the frame.
        hull = np.zeros(self.shape, dtype=np.uint8)
        corner_pts, corner_valid = model.project_points(homography, model.COURT_CORNERS)
        if corner_valid.all():
            clipped = np.clip(corner_pts, [-2 * width, -2 * height], [3 * width, 3 * height])
            cv2.fillConvexPoly(hull, np.rint(clipped).astype(np.int32), 1)

        hull_mask = self.mask & hull
        denominator = int(hull_mask.sum())
        if denominator < 50:
            precision = 0.0
        else:
            precision = float((hull_mask & canvas).sum()) / denominator

        f1 = 0.0
        if recall + precision > 0:
            f1 = 2 * recall * precision / (recall + precision)
        return {
            "line_recall": round(recall, 4),
            "line_precision": round(precision, 4),
            "line_f1": round(f1, 4),
            "in_frame_fraction": round(in_frame_fraction, 4),
        }
