#!/usr/bin/env python3
"""Interactive badminton video scraper.

User flow
---------
1. Run the script.
2. Type a player name, or pick one from a curated list of popular
   world-level players.
3. The script searches YouTube for that player's matches and lists the 10
   most-viewed videos (title, length, view count, link).
4. Select one or more videos to download.
5. The chosen videos are downloaded into ``./videos``.

Usage
-----
    python -m tools.scraper.scrape                 # fully interactive
    python -m tools.scraper.scrape --player "Viktor Axelsen"
    python -m tools.scraper.scrape --player "An Se-young" --results 15 --no-download

Requires the ``scraping`` extra (``yt-dlp`` and ``rich``; ``uv sync --extra
scraping``) plus ``ffmpeg`` on PATH for merging video/audio streams.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.columns import Columns
    from rich.text import Text
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        DownloadColumn,
        TransferSpeedColumn,
        TimeRemainingColumn,
    )
except ImportError:  # pragma: no cover - guidance path
    sys.stderr.write(
        "Missing dependency 'rich'. Install the scraper requirements:\n"
        "    uv sync --extra scraping\n"
    )
    raise SystemExit(1)

try:
    import yt_dlp
except ImportError:  # pragma: no cover - guidance path
    sys.stderr.write(
        "Missing dependency 'yt-dlp'. Install the scraper requirements:\n"
        "    uv sync --extra scraping\n"
    )
    raise SystemExit(1)

from tools.scraper.players import POPULAR_PLAYERS

console = Console()

# Where downloads land. Resolved relative to the repo root (tools/scraper/ -> repo).
REPO_ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = REPO_ROOT / "videos"

# How many raw search hits to pull before ranking by popularity. We
# over-fetch so we can sort by view count and still return a full top-N.
SEARCH_POOL = 40

# YouTube frequently breaks a single player client; trying several in order
# makes extraction/download far more resilient ("page needs to be reloaded"
# and signature errors usually clear on a different client).
YT_EXTRACTOR_ARGS = {"youtube": {"player_client": ["android", "ios", "web"]}}


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def format_duration(seconds: float | int | None) -> str:
    """Render a duration in seconds as H:MM:SS / M:SS."""
    if not seconds:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_views(views: int | None) -> str:
    """Render a view count as a compact human string (1.2M, 34K …)."""
    if views is None:
        return "—"
    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(views)


# --------------------------------------------------------------------------- #
# Player selection
# --------------------------------------------------------------------------- #
def show_player_menu() -> None:
    """Print the curated list of popular players in aligned columns."""
    items: list[Text] = []
    for idx, (name, note) in enumerate(POPULAR_PLAYERS, start=1):
        entry = Text()
        entry.append(f"{idx:>2}. ", style="dim")
        entry.append(name, style="bold cyan")
        entry.append(f"  {note}", style="dim")
        items.append(entry)
    console.print(
        Panel(
            Columns(items, equal=True, expand=True, column_first=True),
            title="[bold]Popular players[/bold]",
            subtitle="[dim]type a number, or type any player name[/dim]",
            border_style="green",
        )
    )


def prompt_for_player(default: str | None = None) -> str:
    """Ask the user for a player: a menu number or a free-text name."""
    if default:
        return default

    show_player_menu()
    while True:
        answer = Prompt.ask(
            "[bold]Player[/bold] (number or name)", console=console
        ).strip()
        if not answer:
            console.print("[yellow]Please enter a number or a name.[/yellow]")
            continue
        if answer.isdigit():
            idx = int(answer)
            if 1 <= idx <= len(POPULAR_PLAYERS):
                return POPULAR_PLAYERS[idx - 1][0]
            console.print(
                f"[yellow]Pick a number between 1 and {len(POPULAR_PLAYERS)}.[/yellow]"
            )
            continue
        return answer


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def search_videos(player: str, limit: int) -> list[dict]:
    """Search YouTube for a player's matches, ranked by view count.

    Returns a list of dicts with keys: title, url, duration, view_count.
    """
    query = f"ytsearch{SEARCH_POOL}:{player} badminton match highlights"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",  # metadata only, no per-video fetch
        "default_search": "ytsearch",
        "noplaylist": True,
        "extractor_args": YT_EXTRACTOR_ARGS,
    }

    with console.status(
        f"[bold green]Searching YouTube for '{player}'…", spinner="dots"
    ):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)

    entries = [e for e in (info or {}).get("entries", []) if e]

    results: list[dict] = []
    for e in entries:
        url = e.get("url") or e.get("webpage_url")
        vid = e.get("id")
        if url and not url.startswith("http") and vid:
            url = f"https://www.youtube.com/watch?v={vid}"
        results.append(
            {
                "title": e.get("title") or "(untitled)",
                "url": url or (f"https://www.youtube.com/watch?v={vid}" if vid else ""),
                "duration": e.get("duration"),
                "view_count": e.get("view_count"),
            }
        )

    # Rank by popularity (view count). Entries with unknown views sink last.
    results.sort(key=lambda r: (r["view_count"] is None, -(r["view_count"] or 0)))
    return results[:limit]


def show_results_table(player: str, videos: list[dict]) -> None:
    """Render the ranked search results as a table."""
    table = Table(
        title=f"Top {len(videos)} results for [bold cyan]{player}[/bold cyan]",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Title", style="bold", ratio=3, no_wrap=False)
    table.add_column("Length", justify="right", width=8)
    table.add_column("Views", justify="right", width=8)
    table.add_column("Link", style="blue", ratio=2, no_wrap=True)

    for idx, v in enumerate(videos, start=1):
        table.add_row(
            str(idx),
            v["title"],
            format_duration(v["duration"]),
            format_views(v["view_count"]),
            v["url"],
        )
    console.print(table)


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
def parse_selection(answer: str, count: int) -> list[int]:
    """Parse a selection string like '1,3,5' or '1-3' or 'all' into indices.

    Returns 0-based indices into the results list. Invalid tokens are skipped.
    """
    answer = answer.strip().lower()
    if answer in {"all", "*"}:
        return list(range(count))
    if answer in {"", "none", "q", "quit"}:
        return []

    chosen: set[int] = set()
    for token in answer.replace(" ", "").split(","):
        if not token:
            continue
        if "-" in token:
            lo, _, hi = token.partition("-")
            if lo.isdigit() and hi.isdigit():
                for n in range(int(lo), int(hi) + 1):
                    if 1 <= n <= count:
                        chosen.add(n - 1)
        elif token.isdigit():
            n = int(token)
            if 1 <= n <= count:
                chosen.add(n - 1)
    return sorted(chosen)


def prompt_for_selection(count: int) -> list[int]:
    """Ask which videos to download (supports ranges, comma lists, 'all')."""
    answer = Prompt.ask(
        "[bold]Download which?[/bold] "
        "[dim](e.g. 1,3,5 or 1-3 or 'all', empty to cancel)[/dim]",
        console=console,
        default="",
    )
    return parse_selection(answer, count)


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def download_videos(videos: list[dict]) -> None:
    """Download the selected videos into DOWNLOAD_DIR with a live progress bar."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[name]}", justify="left"),
        BarColumn(bar_width=None),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )

    # One task per video, created lazily as downloads begin.
    task_ids: dict[str, int] = {}

    def hook(d: dict) -> None:
        info = d.get("info_dict", {})
        key = info.get("id") or info.get("title") or "video"
        name = (info.get("title") or key)[:40]
        if key not in task_ids:
            task_ids[key] = progress.add_task("download", name=name, total=None)
        tid = task_ids[key]

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            progress.update(
                tid,
                total=total,
                completed=d.get("downloaded_bytes", 0),
            )
        elif d["status"] == "finished":
            total = d.get("total_bytes") or d.get("downloaded_bytes")
            progress.update(tid, total=total, completed=total)

    opts = {
        "outtmpl": str(DOWNLOAD_DIR / "%(title)s [%(id)s].%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "ignoreerrors": True,
        "concurrent_fragment_downloads": 4,
        "extractor_args": YT_EXTRACTOR_ARGS,
    }

    urls = [v["url"] for v in videos if v.get("url")]
    console.print(
        f"\n[bold]Downloading {len(urls)} video(s)[/bold] → "
        f"[cyan]{DOWNLOAD_DIR}[/cyan]\n"
    )
    with progress:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download(urls)

    console.print(f"\n[bold green]✓ Done.[/bold green] Saved to [cyan]{DOWNLOAD_DIR}[/cyan]")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run(player_arg: str | None, results: int, do_download: bool) -> int:
    console.print(
        Panel.fit(
            "[bold green]🏸  Badminton Video Scraper[/bold green]\n"
            "[dim]Search & download match videos by player[/dim]",
            border_style="green",
        )
    )

    player = prompt_for_player(player_arg)
    videos = search_videos(player, results)

    if not videos:
        console.print(f"[bold red]No videos found for '{player}'.[/bold red]")
        return 1

    show_results_table(player, videos)

    if not do_download:
        return 0

    indices = prompt_for_selection(len(videos))
    if not indices:
        console.print("[yellow]Nothing selected. Bye![/yellow]")
        return 0

    selected = [videos[i] for i in indices]
    console.print(
        "\n[bold]Selected:[/bold] "
        + ", ".join(f"[cyan]{videos[i]['title'][:40]}[/cyan]" for i in indices)
    )
    download_videos(selected)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interactive badminton video scraper (search & download by player).",
    )
    parser.add_argument(
        "--player", "-p", default=None,
        help="Player name to search (skips the interactive menu).",
    )
    parser.add_argument(
        "--results", "-n", type=int, default=10,
        help="Number of top results to list (default: 10).",
    )
    parser.add_argument(
        "--no-download", action="store_true",
        help="Only search and list results; do not prompt to download.",
    )
    args = parser.parse_args()

    try:
        return run(args.player, args.results, not args.no_download)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Bye![/yellow]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
