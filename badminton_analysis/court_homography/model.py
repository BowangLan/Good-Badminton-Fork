"""Metric badminton court model for homography-based detection.

The court is treated as a planar calibration target: every painted line and
every line intersection ("keypoint lattice") is known in metres from the BWF
spec, so a single 3x3 homography maps the whole model into the image. This is
the shared geometry used by all court_homography strategies.

Coordinate frame: x across the court [0, 6.1], y along it [0, 13.4], origin at
the top-left corner (same convention as badminton_analysis.court.reference).
"""

import cv2
import numpy as np

from ..court.reference import (
    BADMINTON_BACK_SERVICE_OFFSET,
    BADMINTON_COURT_LENGTH,
    BADMINTON_COURT_WIDTH,
    BADMINTON_SERVICE_LINE_FROM_NET,
    BADMINTON_SINGLES_MARGIN,
)

WIDTH = BADMINTON_COURT_WIDTH
LENGTH = BADMINTON_COURT_LENGTH
NET_Y = LENGTH / 2.0
CENTER_X = WIDTH / 2.0

# Painted line positions (net tape excluded — it is not a floor line).
H_LINE_YS = (
    0.0,
    BADMINTON_BACK_SERVICE_OFFSET,                  # 0.76
    NET_Y - BADMINTON_SERVICE_LINE_FROM_NET,        # 4.72
    NET_Y + BADMINTON_SERVICE_LINE_FROM_NET,        # 8.68
    LENGTH - BADMINTON_BACK_SERVICE_OFFSET,         # 12.64
    LENGTH,
)
V_LINE_XS = (
    0.0,
    BADMINTON_SINGLES_MARGIN,                       # 0.46
    CENTER_X,                                       # 3.05
    WIDTH - BADMINTON_SINGLES_MARGIN,               # 5.64
    WIDTH,
)

# Painted segments as ((x1, y1), (x2, y2)) in metres. The centre line only
# exists outside the two service courts.
PAINTED_SEGMENTS = tuple(
    [((0.0, y), (WIDTH, y)) for y in H_LINE_YS]
    + [((x, 0.0), (x, LENGTH)) for x in V_LINE_XS if x != CENTER_X]
    + [
        ((CENTER_X, 0.0), (CENTER_X, H_LINE_YS[2])),
        ((CENTER_X, H_LINE_YS[3]), (CENTER_X, LENGTH)),
    ]
)

COURT_CORNERS = np.array(
    [[0.0, 0.0], [WIDTH, 0.0], [WIDTH, LENGTH], [0.0, LENGTH]], dtype=np.float32
)


def _junction_type(x, y):
    """Classify a lattice point by how many painted arms leave it: X/T/L."""
    arms = 0
    for (x1, y1), (x2, y2) in PAINTED_SEGMENTS:
        if x1 == x2 == x and min(y1, y2) <= y <= max(y1, y2):  # vertical through point
            arms += int(y > min(y1, y2)) + int(y < max(y1, y2))
        elif y1 == y2 == y and min(x1, x2) <= x <= max(x1, x2):  # horizontal
            arms += int(x > min(x1, x2)) + int(x < max(x1, x2))
    return {4: "X", 3: "T", 2: "L"}.get(arms, "?")


def _build_lattice():
    points, types = [], []
    for y in H_LINE_YS:
        for x in V_LINE_XS:
            kind = _junction_type(x, y)
            if kind != "?":
                points.append((x, y))
                types.append(kind)
    return np.array(points, dtype=np.float32), tuple(types)


# 30 keypoints: every intersection of painted lines that physically exists.
LATTICE_POINTS, LATTICE_TYPES = _build_lattice()


def dense_line_samples(step_m=0.05):
    """Sample every painted segment at *step_m* resolution.

    Returns (points Nx2 float32 in metres, line_id N int32) so scorers can
    reason per line as well as globally.
    """
    pts, ids = [], []
    for idx, ((x1, y1), (x2, y2)) in enumerate(PAINTED_SEGMENTS):
        length = float(np.hypot(x2 - x1, y2 - y1))
        count = max(2, int(round(length / step_m)) + 1)
        t = np.linspace(0.0, 1.0, count)
        pts.append(np.column_stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t]))
        ids.append(np.full(count, idx, dtype=np.int32))
    return np.vstack(pts).astype(np.float32), np.concatenate(ids)


def project_points(homography, points_m):
    """Project Nx2 metre points through a model->image homography.

    Returns (image_points Nx2 float32, valid N bool) where valid marks points
    with a safely positive homogeneous w (in front of the horizon).
    """
    pts = np.asarray(points_m, dtype=np.float64)
    ones = np.ones((len(pts), 1))
    proj = np.hstack([pts, ones]) @ np.asarray(homography, dtype=np.float64).T
    w = proj[:, 2]
    valid = np.abs(w) > 1e-9
    safe_w = np.where(valid, w, 1.0)
    image_pts = proj[:, :2] / safe_w[:, None]
    if valid.any():
        # Points whose w flips sign are behind the horizon and project to
        # spurious locations — keep only the dominant sign.
        sign = 1.0 if np.median(w[valid]) > 0 else -1.0
        valid &= (w * sign) > 1e-9
    return image_pts.astype(np.float32), valid


def homography_from_corners(image_corners):
    """Homography (model metres -> image px) from the 4 outer court corners,
    ordered top-left, top-right, bottom-right, bottom-left."""
    corners = np.array(image_corners, dtype=np.float32).reshape(4, 2)
    return cv2.getPerspectiveTransform(COURT_CORNERS, corners)


def quad_plausible(corners, image_shape):
    """Basic sanity for a 4-point (TL, TR, BR, BL) image quad hypothesis."""
    height, width = image_shape[:2]
    pts = np.array(corners, dtype=np.float32)
    if not np.isfinite(pts).all():
        return False
    if len(cv2.convexHull(pts)) != 4:
        return False
    area = abs(cv2.contourArea(pts))
    if area < width * height * 0.06:
        return False
    # Broadcast views: far edge above near edge, near edge wider or similar.
    top_y = (pts[0, 1] + pts[1, 1]) / 2.0
    bottom_y = (pts[2, 1] + pts[3, 1]) / 2.0
    if bottom_y - top_y < height * 0.18:
        return False
    return True


def full_court_plausible(homography, image_shape):
    """Sanity for a model->image homography: the projected full court must be
    a convex, sanely sized quad with the near baseline below the far one."""
    height, width = image_shape[:2]
    corners, valid = project_points(homography, COURT_CORNERS)
    if not valid.all() or not np.isfinite(corners).all():
        return False
    if np.abs(corners).max() > 8 * max(width, height):
        return False
    if len(cv2.convexHull(corners.astype(np.float32))) != 4:
        return False
    area = abs(cv2.contourArea(corners.astype(np.float32)))
    if not (0.10 * width * height <= area <= 6.0 * width * height):
        return False
    if (corners[2, 1] + corners[3, 1]) / 2.0 <= (corners[0, 1] + corners[1, 1]) / 2.0:
        return False
    return True


def lattice_in_frame(homography, image_shape, margin=0.0):
    """Project the keypoint lattice; return (points Nx2, types list, in_frame N bool)."""
    height, width = image_shape[:2]
    pts, valid = project_points(homography, LATTICE_POINTS)
    in_frame = (
        valid
        & (pts[:, 0] >= -margin)
        & (pts[:, 0] <= width - 1 + margin)
        & (pts[:, 1] >= -margin)
        & (pts[:, 1] <= height - 1 + margin)
    )
    return pts, list(LATTICE_TYPES), in_frame
