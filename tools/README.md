# tools

Helper scripts for scraping badminton match videos from YouTube.

Requires [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) on `PATH` (or at `~/.local/bin/yt-dlp`)
and `ffmpeg`. Run both from the repo root.

## Usage

```bash
# 1. Search YouTube for each player's most-viewed edited highlight (1-25 min),
#    dedupe, and write the chosen video ids to tools/plan.json
python tools/pick_videos.py

# 2. Download every video in the plan to ./videos as NN_Player.mp4 (<=720p)
python tools/download_videos.py
```

- `pick_videos.py` — player list + queries; picks the most-viewed highlight per player.
- `download_videos.py` — downloads the picks from `tools/plan.json`.

`tools/plan.json` is a generated artifact and is git-ignored.
