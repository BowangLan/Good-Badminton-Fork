"""Quick standalone tester for the court line detection algorithm.

Runs auto_detect_court_corners on one or more images, prints the detection
score + sub-scores, and writes an annotated preview PNG next to each input
(or into --out-dir). No GUI required; pass --show to pop a window.

Examples:
    uv run python -m tools.test_court_detection templates/demo.png
    uv run python -m tools.test_court_detection templates/*.png --out-dir /tmp/court
    uv run python -m tools.test_court_detection templates/demo.png --show
"""

import argparse
import glob
import os

import cv2

from badminton_analysis.court.detector import (
    auto_detect_court_corners,
    render_auto_court_preview,
)
from badminton_analysis.court.mapper import compute_expanded_roi

# The pipeline always detects on a 1080x720 resize (see mapper.auto_detect_preview).
FIXED_SIZE = (1080, 720)


def test_image(path, out_dir=None, show=False):
    image = cv2.imread(path)
    if image is None:
        print(f"[SKIP] cannot read: {path}")
        return

    base = cv2.resize(image, FIXED_SIZE)
    corners, _mask, debug = auto_detect_court_corners(base)

    print(f"\n=== {path} ===")
    if corners:
        print(f"  corners (1080x720): {corners}")
        print(f"  total score       : {debug.get('score'):.2f}")
        details = debug.get("details") or {}
        for key in sorted(details):
            print(f"    {key:32s}: {details[key]}")
        roi = compute_expanded_roi(corners, base.shape)
        preview = render_auto_court_preview(base, corners, roi, debug)
    else:
        print("  NO COURT DETECTED")
        print(f"    horizontal segments: {len(debug.get('horizontal', []))}")
        print(f"    side segments      : {len(debug.get('side', []))}")
        preview = render_auto_court_preview(base, None, None, debug)

    stem = os.path.splitext(os.path.basename(path))[0]
    out_dir = out_dir or os.path.dirname(os.path.abspath(path))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{stem}_court_preview.png")
    cv2.imwrite(out_path, preview)
    print(f"  preview saved      : {out_path}")

    if show:
        cv2.imshow(f"court: {stem}", preview)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", help="image path(s) or globs")
    parser.add_argument("--out-dir", default=None, help="where to write previews (default: alongside input)")
    parser.add_argument("--show", action="store_true", help="display each preview in a window")
    args = parser.parse_args()

    paths = []
    for pattern in args.images:
        paths.extend(sorted(glob.glob(pattern)) or [pattern])

    for path in paths:
        test_image(path, out_dir=args.out_dir, show=args.show)


if __name__ == "__main__":
    main()
