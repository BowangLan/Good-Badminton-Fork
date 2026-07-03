"""Line-pixel extraction front ends.

The green-gated HSV mask from badminton_analysis.court.detector assumes a
green court on a darker surround; bright arenas or pale mats flood it (whole
floor passes the white threshold) and side lines disappear. Court lines are
always THIN bright structures though, so a morphological white top-hat
responds to them regardless of court colour. Both front ends produce the same
(horizontal, side, mask) shape so every fitting strategy can run on either.
"""

import cv2
import numpy as np

from ..court.detector import (
    _dedupe_lines,
    _line_angle,
    detect_court_line_segments,
)


def tophat_line_mask(image, kernel_px=15):
    """Thin bright line pixels, court-colour agnostic.

    White top-hat with a kernel wider than any court line keeps only thin
    bright ridges; an HSV whiteness gate then drops coloured thin clutter
    (logos, mat seams).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_px, kernel_px))
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    _otsu, binary = cv2.threshold(tophat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    _h, s, v = cv2.split(hsv)
    whitish = ((s <= 110) & (v >= 110)).astype(np.uint8) * 255

    mask = cv2.bitwise_and(binary, whitish)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3)), iterations=1
    )
    return mask


def detect_segments_tophat(image):
    """Same output contract as detect_court_line_segments, over the top-hat mask."""
    height, width = image.shape[:2]
    mask = tophat_line_mask(image)
    min_line_length = max(40, int(min(width, height) * 0.09))
    max_gap = max(12, int(min(width, height) * 0.04))
    raw_lines = cv2.HoughLinesP(
        mask,
        rho=1,
        theta=np.pi / 180,
        threshold=55,
        minLineLength=min_line_length,
        maxLineGap=max_gap,
    )
    if raw_lines is None:
        return [], [], mask

    edge_margin = max(8, int(min(width, height) * 0.015))
    horizontal, side = [], []
    for raw in raw_lines[:, 0, :]:
        x1, y1, x2, y2 = [int(v) for v in raw]
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < min_line_length:
            continue
        if (
            min(x1, x2) <= edge_margin
            or max(x1, x2) >= width - 1 - edge_margin
            or min(y1, y2) <= edge_margin
            or max(y1, y2) >= height - 1 - edge_margin
        ):
            continue
        angle = _line_angle(x1, y1, x2, y2)
        segment = {
            "points": (x1, y1, x2, y2),
            "length": length,
            "mid": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            "angle": angle,
        }
        if min(angle, 180 - angle) <= 16:
            horizontal.append(segment)
        elif 45 <= angle <= 135:
            side.append(segment)

    return _dedupe_lines(horizontal, "horizontal", 14), _dedupe_lines(side, "side", 18), mask


FRONT_ENDS = {
    "hsv": detect_court_line_segments,
    "tophat": detect_segments_tophat,
}
