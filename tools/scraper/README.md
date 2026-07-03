# Badminton Video Scraper

Interactive CLI to search & download badminton match videos by player name,
straight into the project's `videos/` folder (the same folder the analysis
pipeline reads from).

## Requirements

Needs [`ffmpeg`](https://ffmpeg.org/) on your `PATH` (used to merge the best
video + audio streams). On macOS: `brew install ffmpeg`.

Python deps (`yt-dlp`, `rich`) live in the `scraping` extra in `pyproject.toml`.

## Usage

Run from the repo root — `uv run --extra scraping` resolves the deps on the fly:

```bash
uv run --extra scraping python -m tools.scraper.scrape
```

Prefer a persistent environment? Sync the extra once, then run plainly:

```bash
uv sync --extra scraping
python -m tools.scraper.scrape
```

Flow:

1. Type a **player name**, or pick a number from the list of popular
   world-level players.
2. The scraper lists the **10 most-viewed** videos — title, length, view
   count and link.
3. Enter which to download: `1,3,5`, a range `1-3`, `all`, or empty to cancel.
4. Selected videos download into `./videos/` with a live progress bar.

### Options

```bash
uv run --extra scraping python -m tools.scraper.scrape --player "Viktor Axelsen"   # skip the menu
uv run --extra scraping python -m tools.scraper.scrape --results 15                 # list top 15 instead of 10
uv run --extra scraping python -m tools.scraper.scrape --no-download                # just search & list
```

| Flag | Description |
| --- | --- |
| `-p`, `--player` | Player name; skips the interactive menu. |
| `-n`, `--results` | Number of top results to list (default 10). |
| `--no-download` | Search and list only, don't prompt to download. |

## Notes

- Results are ranked by view count (a proxy for "most popular").
- If YouTube extraction fails, upgrade yt-dlp: `uv pip install -U yt-dlp`.
- Downloaded files are git-ignored; the tracked `demo*.mp4` clips are kept.
