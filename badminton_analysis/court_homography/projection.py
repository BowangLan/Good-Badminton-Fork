"""1-D projection detection (histogram-voting pipeline).

Instead of fitting line equations (Hough-style parameter voting), this follows
the 1-D projection idea: after rectifying perspective away, every court line
family collapses onto one axis, so line POSITIONS become peaks of a 1-D
histogram which can be matched against the known model spacing.

Pipeline:
  Hough segments (reused, for direction only) -> vanishing point per family ->
  projective+affine rectification sending both VPs to infinity -> project
  white-line pixels onto rows/columns -> coverage-normalized 1-D profiles ->
  peak detection -> match peak patterns to model line positions (spacing
  ratios are preserved under the affine ambiguity) -> homography.
"""

import itertools

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from ..court.detector import detect_court_line_segments
from . import model
from .hough_fit import _full_court_plausible

CANVAS = 900.0  # rectified working extent, px


def _fit_vanishing_point(segments, angle_tol_deg=2.0):
    """Robust vanishing point of one segment family.

    Least squares over all segments gets dragged by clutter (net posts,
    banner edges misclassified into the family), which skews the whole
    rectification. Instead: every segment pair votes a VP candidate, the one
    consistent with the most segment length wins, then a least-squares refit
    on its inliers.
    """
    lines, mids, dirs, weights = [], [], [], []
    for seg in segments:
        x1, y1, x2, y2 = seg["points"]
        line = np.cross([x1, y1, 1.0], [x2, y2, 1.0])
        norm = np.hypot(line[0], line[1])
        if norm < 1e-9:
            continue
        lines.append(line / norm)
        mids.append(seg["mid"])
        dirs.append(np.array([x2 - x1, y2 - y1]) / max(seg["length"], 1e-9))
        weights.append(seg["length"])
    if len(lines) < 2:
        return None
    lines = np.asarray(lines)
    mids = np.asarray(mids, dtype=np.float64)
    dirs = np.asarray(dirs)
    weights = np.asarray(weights)

    def inliers_of(vp):
        # Direction from each midpoint toward the VP (works for finite and
        # infinite VPs via homogeneous coords).
        to_vp = np.column_stack([vp[0] - mids[:, 0] * vp[2], vp[1] - mids[:, 1] * vp[2]])
        norms = np.linalg.norm(to_vp, axis=1)
        ok = norms > 1e-9
        cos = np.zeros(len(mids))
        cos[ok] = np.abs(np.sum(to_vp[ok] * dirs[ok], axis=1)) / norms[ok]
        return cos >= np.cos(np.radians(angle_tol_deg))

    best_mask, best_score = None, -1.0
    for i, j in itertools.combinations(range(len(lines)), 2):
        candidate = np.cross(lines[i], lines[j])
        if np.abs(candidate).max() < 1e-12:
            continue
        mask = inliers_of(candidate)
        score = float(weights[mask].sum())
        if score > best_score:
            best_score, best_mask = score, mask
    if best_mask is None or best_mask.sum() < 2:
        return None
    _u, _s, vt = np.linalg.svd(lines[best_mask] * weights[best_mask, None])
    return vt[-1]


def _rectifier(vp_h, vp_v):
    """Homography sending both VPs to infinity, with the horizontal family
    mapped to image-x and the vertical family to image-y."""
    vanishing_line = np.cross(vp_h, vp_v)
    if abs(vanishing_line[2]) < 1e-12:
        vanishing_line = vanishing_line + np.array([0.0, 0.0, 1e-12])
    vanishing_line = vanishing_line / vanishing_line[2]
    projective = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [vanishing_line[0], vanishing_line[1], 1.0]]
    )

    direction_h = (projective @ vp_h)[:2]
    direction_v = (projective @ vp_v)[:2]
    if np.linalg.norm(direction_h) < 1e-9 or np.linalg.norm(direction_v) < 1e-9:
        return None
    direction_h /= np.linalg.norm(direction_h)
    rotation = np.array(
        [[direction_h[0], direction_h[1], 0.0],
         [-direction_h[1], direction_h[0], 0.0],
         [0.0, 0.0, 1.0]]
    )
    direction_v = rotation[:2, :2] @ direction_v
    if abs(direction_v[1]) < 1e-6:
        return None  # families (near-)parallel — no usable rectification
    shear = np.array(
        [[1.0, -direction_v[0] / direction_v[1], 0.0],
         [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0]]
    )
    return shear @ rotation @ projective


def _transform(points_xy, homography):
    pts = np.hstack([points_xy, np.ones((len(points_xy), 1))]) @ homography.T
    w = pts[:, 2]
    valid = np.abs(w) > 1e-9
    if valid.any():
        sign = 1.0 if np.median(w[valid]) > 0 else -1.0
        valid &= (w * sign) > 1e-9
    out = pts[:, :2] / np.where(valid, w, 1.0)[:, None]
    return out, valid


def _profiles(line_mask, rectify, h_segments, v_segments):
    """Coverage-normalized 1-D histograms of line pixels along both axes.

    The canvas is scaled PER AXIS from the rectified extent of the detected
    segment midpoints. Perspective squeezes the court length into a sliver of
    the rectified plane (the 0.76 m doubles-service gaps can collapse below
    peak resolution), and clutter pixels near the horizon blow up any extent
    computed from raw mask pixels — segment midpoints suffer neither.
    """
    ys, xs = np.nonzero(line_mask)
    if len(xs) < 200:
        return None
    line_pts, line_ok = _transform(np.column_stack([xs, ys]).astype(np.float64), rectify)
    line_pts = line_pts[line_ok]
    if len(line_pts) < 200:
        return None

    h_mids, h_ok = _transform(
        np.array([seg["mid"] for seg in h_segments], dtype=np.float64), rectify
    )
    v_mids, v_ok = _transform(
        np.array([seg["mid"] for seg in v_segments], dtype=np.float64), rectify
    )
    if h_ok.sum() < 2 or v_ok.sum() < 2:
        return None
    lo = np.array([v_mids[v_ok, 0].min(), h_mids[h_ok, 1].min()])
    hi = np.array([v_mids[v_ok, 0].max(), h_mids[h_ok, 1].max()])
    margin = np.maximum((hi - lo) * 0.15, 1e-6)
    lo, hi = lo - margin, hi + margin
    span = np.maximum(hi - lo, 1e-6)
    scale = CANVAS / span  # anisotropic: each axis fills the canvas
    to_canvas = np.array(
        [[scale[0], 0.0, -lo[0] * scale[0]],
         [0.0, scale[1], -lo[1] * scale[1]],
         [0.0, 0.0, 1.0]]
    )
    full = to_canvas @ rectify

    line_pts = line_pts * scale - lo * scale
    keep = (
        (line_pts[:, 0] >= 0) & (line_pts[:, 0] < CANVAS)
        & (line_pts[:, 1] >= 0) & (line_pts[:, 1] < CANVAS)
    )
    line_pts = line_pts[keep]
    if len(line_pts) < 200:
        return None

    # Coverage of the whole frame, for density normalization.
    height, width = line_mask.shape[:2]
    grid_y, grid_x = np.mgrid[0:height:4, 0:width:4]
    grid = np.column_stack([grid_x.ravel(), grid_y.ravel()]).astype(np.float64)
    grid_pts, grid_ok = _transform(grid, full)
    grid_pts = grid_pts[grid_ok]
    gk = (
        (grid_pts[:, 0] >= 0) & (grid_pts[:, 0] < CANVAS)
        & (grid_pts[:, 1] >= 0) & (grid_pts[:, 1] < CANVAS)
    )
    grid_pts = grid_pts[gk]

    bins = int(CANVAS)
    result = {}
    for axis, name in ((1, "rows"), (0, "cols")):
        counts = np.bincount(line_pts[:, axis].astype(np.int64), minlength=bins)[:bins]
        coverage = np.bincount(grid_pts[:, axis].astype(np.int64), minlength=bins)[:bins]
        profile = counts / np.maximum(coverage, coverage.max() * 0.05 + 1e-9)
        result[name] = gaussian_filter1d(profile.astype(np.float64), sigma=2.5)
    result["homography"] = full
    return result


def _peaks(profile):
    if profile.max() <= 0:
        return np.array([]), np.array([])
    positions, props = find_peaks(
        profile,
        height=profile.max() * 0.12,
        distance=12,
        prominence=profile.max() * 0.08,
    )
    return positions.astype(np.float64), props["peak_heights"]


def _match_positions(peak_pos, peak_weight, model_pos, min_matched=3, keep=5):
    """Affine maps model_pos -> peak axis that explain the peaks, best first.

    Ratios of line spacings survive the affine ambiguity of rectification, so
    trying every (peak pair, model pair) correspondence and scoring how well
    the remaining model lines land on peaks is exact, not heuristic. Returns
    up to *keep* distinct fits as (score, scale, offset, n_matched) — the
    internal peak score can prefer a wrong assignment, so the caller should
    judge combinations rather than trust the top one.
    """
    model_pos = np.asarray(model_pos, dtype=np.float64)
    tol = CANVAS * 0.015
    fits = []
    for (i, j) in itertools.combinations(range(len(peak_pos)), 2):
        for (k, l) in itertools.combinations(range(len(model_pos)), 2):
            scale = (peak_pos[j] - peak_pos[i]) / (model_pos[l] - model_pos[k])
            if scale <= 0:
                continue
            extent = scale * (model_pos[-1] - model_pos[0])
            if not (CANVAS * 0.15 <= extent <= CANVAS * 1.6):
                continue
            offset = peak_pos[i] - scale * model_pos[k]
            predicted = scale * model_pos + offset
            dist = np.abs(predicted[:, None] - peak_pos[None, :])
            nearest = dist.argmin(axis=1)
            near_dist = dist[np.arange(len(model_pos)), nearest]
            matched = near_dist <= tol
            if matched.sum() < min_matched:
                continue
            score = float(
                np.sum(peak_weight[nearest[matched]] * (1.0 - near_dist[matched] / tol))
            ) + matched.sum() * 0.5
            fits.append((score, scale, offset, int(matched.sum())))

    fits.sort(key=lambda f: f[0], reverse=True)
    distinct = []
    for fit in fits:
        if all(
            abs(fit[1] - kept[1]) > 0.02 * abs(kept[1]) or abs(fit[2] - kept[2]) > tol
            for kept in distinct
        ):
            distinct.append(fit)
        if len(distinct) >= keep:
            break
    return distinct


def detect(image, judge, segments=None):
    """Return (homography or None, debug dict).

    segments: optional precomputed (horizontal, side, mask) from any front
    end in extraction.FRONT_ENDS; defaults to the HSV green-gated one.
    """
    horizontal, side, seg_mask = segments or detect_court_line_segments(image)
    debug = {"n_horizontal": len(horizontal), "n_side": len(side), "mask": seg_mask}
    if len(horizontal) < 2 or len(side) < 2:
        return None, debug

    vp_h = _fit_vanishing_point(horizontal)
    vp_v = _fit_vanishing_point(side)
    if vp_h is None or vp_v is None:
        return None, debug
    rectify = _rectifier(vp_h, vp_v)
    if rectify is None:
        return None, debug

    profiles = _profiles(judge.mask, rectify, horizontal, side)
    if profiles is None:
        return None, debug

    row_pos, row_w = _peaks(profiles["rows"])
    col_pos, col_w = _peaks(profiles["cols"])
    debug["n_row_peaks"] = len(row_pos)
    debug["n_col_peaks"] = len(col_pos)
    if len(row_pos) < 2 or len(col_pos) < 2:
        return None, debug

    row_fits = _match_positions(row_pos, row_w, model.H_LINE_YS, min_matched=3)
    col_fits = _match_positions(col_pos, col_w, model.V_LINE_XS, min_matched=3)
    if not row_fits or not col_fits:
        return None, debug

    # The internal peak score can prefer a wrong assignment — judge every
    # row-fit x col-fit combination against the mask and keep the best.
    # Recall-only quick_score is not enough here (a wrong assignment that
    # squeezes many model lines onto few image lines has high recall), so
    # the top candidates get the full precision-aware score.
    back = np.linalg.inv(profiles["homography"])
    candidates = []
    for row_fit in row_fits:
        for col_fit in col_fits:
            _rs, a_y, b_y, rows_matched = row_fit
            _cs, a_x, b_x, cols_matched = col_fit
            corners_rect = np.column_stack(
                [a_x * model.COURT_CORNERS[:, 0] + b_x,
                 a_y * model.COURT_CORNERS[:, 1] + b_y]
            )
            corners_img, ok = _transform(corners_rect.astype(np.float64), back)
            if not ok.all():
                continue
            homography = model.homography_from_corners(corners_img)
            if not _full_court_plausible(homography, image.shape):
                continue
            quick = judge.quick_score(homography)
            if quick > 0.25:
                candidates.append((quick, homography, (rows_matched, cols_matched)))

    if not candidates:
        return None, debug
    # At most keep x keep combinations survive — full-judge them all.
    candidates.sort(key=lambda c: c[0], reverse=True)
    best_h, best_f1, best_fits = None, -1.0, None
    for _quick, homography, fits in candidates:
        f1 = judge.score(homography)["line_f1"]
        if f1 > best_f1:
            best_h, best_f1, best_fits = homography, f1, fits
    debug["rows_matched"], debug["cols_matched"] = best_fits
    return best_h, debug
