import subprocess, json, os
YTDLP = os.path.expanduser("~/.local/bin/yt-dlp")
plan = json.load(open("tools/plan.json"))
os.makedirs("videos", exist_ok=True)
for name, vid in plan.items():
    print(f"\n=== Downloading {name} ({vid}) ===", flush=True)
    cmd = [
        YTDLP, "--no-warnings", "--newline",
        "-f", "bv*[height<=720]+ba/b[height<=720]/b",
        "--merge-output-format", "mp4",
        "-o", f"videos/{name}.%(ext)s",
        f"https://www.youtube.com/watch?v={vid}",
    ]
    r = subprocess.run(cmd)
    print(f"--- {name} exit {r.returncode} ---", flush=True)
print("\nALL DONE")
