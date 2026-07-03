"""Extract random frames from videos to build a benchmark image dataset.

Selects videos whose filename matches a regex, picks N random frames from each,
and writes them into N "set" subfolders (set1..setN) — so each set holds one
frame per video, giving comparable input sets you can benchmark together or
separately.

Example (used to seed the court-detection benchmark):
    uv run python -m tools.extract_benchmark_frames \\
        --videos-dir videos --pattern '^0[0-9]_' \\
        --out benchmarks/artifacts/data/court_detection --frames-per-video 2 --seed 42
"""

import argparse
import os
import random
import re

import cv2


def pick_frame_indices(total, count, seed_key, margin=0.1):
    """Pick `count` distinct frame indices from the middle (1-margin) of a clip."""
    lo = int(total * margin)
    hi = int(total * (1.0 - margin))
    if hi - lo < count:
        lo, hi = 0, max(total - 1, count)
    rng = random.Random(seed_key)
    return sorted(rng.sample(range(lo, hi), count))


def extract(video_path, indices):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        frames.append(frame if ok else None)
    cap.release()
    return frames


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--videos-dir", default="videos")
    parser.add_argument("--pattern", default=r"^0[0-9]_", help="regex matched against filenames")
    parser.add_argument("--out", required=True, help="output dataset dir (setN subfolders created inside)")
    parser.add_argument("--frames-per-video", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    regex = re.compile(args.pattern)
    videos = sorted(
        f for f in os.listdir(args.videos_dir)
        if regex.search(f) and f.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm"))
    )
    if not videos:
        print(f"No videos matching {args.pattern!r} in {args.videos_dir}")
        return 1

    set_dirs = [os.path.join(args.out, f"set{i + 1}") for i in range(args.frames_per_video)]
    for d in set_dirs:
        os.makedirs(d, exist_ok=True)

    print(f"Matched {len(videos)} videos; extracting {args.frames_per_video} frame(s) each.\n")
    written = 0
    for name in videos:
        stem = os.path.splitext(name)[0]
        path = os.path.join(args.videos_dir, name)
        cap = cv2.VideoCapture(path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        if total <= 0:
            print(f"  [skip] cannot read frames: {name}")
            continue

        indices = pick_frame_indices(total, args.frames_per_video, f"{args.seed}:{stem}")
        frames = extract(path, indices)
        for set_i, (idx, frame) in enumerate(zip(indices, frames)):
            if frame is None:
                print(f"  [skip] frame {idx} unreadable in {name}")
                continue
            out_path = os.path.join(set_dirs[set_i], f"{stem}.png")
            cv2.imwrite(out_path, frame)
            written += 1
        print(f"  {stem}: frames {indices} -> {', '.join(f'set{i+1}' for i in range(len(frames)))}")

    print(f"\nWrote {written} frames into: {', '.join(set_dirs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
