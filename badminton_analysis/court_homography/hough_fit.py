"""Classical model-fitting detection (Farin-style pipeline).

white-line mask -> Hough segments -> enumerate correspondences between
detected line pairs and KNOWN model lines -> homography per hypothesis ->
pick the one whose full projected court model is best supported by the mask.

This generalizes badminton_analysis.court.detector: that detector assumes the
four chosen segments are the outer boundary, while here a pair of detected
horizontals may be (baseline, short service line) or any other plausible
assignment — so partial views and frames where the boundary is occluded can
still lock onto inner lines.
"""

import itertools

import cv2
import numpy as np

from ..court.detector import _line_intersection, detect_court_line_segments
from . import model


def _plausible_assignments():
    """Model line pairs a detected (top, bottom) / (left, right) pair may be."""
    h_pairs = [
        (ya, yb)
        for ya, yb in itertools.combinations(model.H_LINE_YS, 2)
        if yb - ya >= 3.9  # closer pairs give ill-conditioned homographies
    ]
    v_pairs = [
        (xa, xb)
        for xa, xb in itertools.combinations(model.V_LINE_XS, 2)
        if xb - xa >= 5.0 and model.CENTER_X not in (xa, xb)
    ]
    return h_pairs, v_pairs


H_ASSIGNMENTS, V_ASSIGNMENTS = _plausible_assignments()


# Shared plausibility gates live on the model; keep the old private names
# for in-package callers.
_quad_plausible = model.quad_plausible
_full_court_plausible = model.full_court_plausible


def detect(image, judge, max_h=7, max_v=7, keep_top=10, segments=None):
    """Return (homography or None, debug dict).

    segments: optional precomputed (horizontal, side, mask) from any front
    end in extraction.FRONT_ENDS; defaults to the HSV green-gated one.
    """
    horizontal, side, mask = segments or detect_court_line_segments(image)
    debug = {
        "n_horizontal": len(horizontal),
        "n_side": len(side),
        "hypotheses": 0,
        "mask": mask,
    }
    if len(horizontal) < 2 or len(side) < 2:
        return None, debug

    height, width = image.shape[:2]
    horizontals = sorted(horizontal, key=lambda s: s["length"], reverse=True)[:max_h]
    horizontals.sort(key=lambda s: s["mid"][1])
    sides = sorted(side, key=lambda s: s["length"], reverse=True)[:max_v]
    sides.sort(key=lambda s: s["mid"][0])

    candidates = []  # (quick_score, homography)
    hypothesis_count = 0
    for i, top in enumerate(horizontals):
        for bottom in horizontals[i + 1:]:
            if bottom["mid"][1] - top["mid"][1] < height * 0.18:
                continue
            for j, left in enumerate(sides):
                for right in sides[j + 1:]:
                    if right["mid"][0] - left["mid"][0] < width * 0.18:
                        continue
                    corners = [
                        _line_intersection(top["points"], left["points"]),
                        _line_intersection(top["points"], right["points"]),
                        _line_intersection(bottom["points"], right["points"]),
                        _line_intersection(bottom["points"], left["points"]),
                    ]
                    if any(c is None for c in corners):
                        continue
                    if not _quad_plausible(corners, image.shape):
                        continue
                    image_quad = np.array(corners, dtype=np.float32)

                    for ya, yb in H_ASSIGNMENTS:
                        for xa, xb in V_ASSIGNMENTS:
                            model_quad = np.array(
                                [[xa, ya], [xb, ya], [xb, yb], [xa, yb]],
                                dtype=np.float32,
                            )
                            homography = cv2.getPerspectiveTransform(model_quad, image_quad)
                            hypothesis_count += 1
                            if not _full_court_plausible(homography, image.shape):
                                continue
                            quick = judge.quick_score(homography)
                            if quick > 0.3:
                                candidates.append((quick, homography))

    debug["hypotheses"] = hypothesis_count
    if not candidates:
        return None, debug

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_h, best_f1 = None, -1.0
    for _quick, homography in candidates[:keep_top]:
        scores = judge.score(homography)
        if scores["line_f1"] > best_f1:
            best_f1, best_h = scores["line_f1"], homography
    debug["candidates"] = len(candidates)
    return best_h, debug
