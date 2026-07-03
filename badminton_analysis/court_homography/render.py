"""Preview rendering for homography-based court detections."""

import cv2
import numpy as np

from . import model

_TYPE_COLORS = {"L": (0, 0, 255), "T": (0, 140, 255), "X": (255, 0, 255)}


def render_preview(image, homography, banner="", debug=None):
    preview = image.copy()

    if homography is None:
        if debug:
            for line in debug.get("horizontal_segments", []):
                cv2.line(preview, line["points"][:2], line["points"][2:], (0, 220, 255), 2)
            for line in debug.get("side_segments", []):
                cv2.line(preview, line["points"][:2], line["points"][2:], (255, 180, 0), 2)
    else:
        pts, ids = model.dense_line_samples(step_m=0.10)
        projected, valid = model.project_points(homography, pts)
        height, width = preview.shape[:2]
        in_frame = (
            valid
            & (projected[:, 0] >= 0) & (projected[:, 0] <= width - 1)
            & (projected[:, 1] >= 0) & (projected[:, 1] <= height - 1)
        )
        rounded = np.rint(projected).astype(np.int32)
        drawable = (ids[:-1] == ids[1:]) & in_frame[:-1] & in_frame[1:]
        for idx in np.flatnonzero(drawable):
            cv2.line(preview, tuple(rounded[idx]), tuple(rounded[idx + 1]),
                     (0, 255, 0), 2, cv2.LINE_AA)

        lattice_pts, types, lattice_in = model.lattice_in_frame(homography, preview.shape)
        for point, kind, visible in zip(lattice_pts, types, lattice_in):
            if not visible:
                continue
            center = tuple(np.rint(point).astype(int))
            cv2.circle(preview, center, 5, _TYPE_COLORS[kind], -1, cv2.LINE_AA)

    cv2.rectangle(preview, (0, 0), (preview.shape[1], 40), (0, 0, 0), -1)
    cv2.putText(preview, banner, (14, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.68,
                (255, 255, 255), 2, cv2.LINE_AA)
    return preview
