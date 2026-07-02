import subprocess, json, sys, os
YTDLP = os.path.expanduser("~/.local/bin/yt-dlp")

# 10 famous men's singles players -> query for their most iconic/popular match highlights
PLAYERS = [
    ("01_Lin_Dan",         "Lin Dan vs Lee Chong Wei 2012 Olympic final badminton highlights"),
    ("02_Lee_Chong_Wei",   "Lee Chong Wei vs Lin Dan 2011 World Championship final badminton highlights"),
    ("03_Viktor_Axelsen",  "Viktor Axelsen vs Chen Long Tokyo 2020 Olympic final badminton highlights"),
    ("04_Kento_Momota",    "Kento Momota best match badminton highlights"),
    ("05_Chen_Long",       "Chen Long vs Lee Chong Wei 2016 Olympic final badminton highlights"),
    ("06_Taufik_Hidayat",  "Taufik Hidayat 2004 Olympic final badminton highlights"),
    ("07_Lee_Zii_Jia",     "Lee Zii Jia All England 2021 final badminton highlights"),
    ("08_Anthony_Ginting", "Anthony Ginting vs Viktor Axelsen badminton highlights"),
    ("09_Kidambi_Srikanth","Kidambi Srikanth vs Viktor Axelsen badminton highlights"),
    ("10_Loh_Kean_Yew",    "Loh Kean Yew vs Kento Momota badminton highlights"),
]

MIN_DUR = 60        # skip <1min shorts
MAX_DUR = 25 * 60   # skip full replays (>25min)
N = 15              # candidates to inspect

def pick(query):
    # search sorted by view count
    url = f"ytsearch{N}:{query}"
    cmd = [YTDLP, "--no-warnings", "--flat-playlist", "-j", url]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    cands = []
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        dur = d.get("duration") or 0
        vc = d.get("view_count") or 0
        if MIN_DUR <= dur <= MAX_DUR:
            cands.append((vc, dur, d.get("title"), d.get("id")))
    cands.sort(reverse=True)  # most viewed first
    return cands

if __name__ == "__main__":
    plan = {}
    used = set()
    for name, q in PLAYERS:
        c = pick(q)
        chosen = None
        for vc, dur, title, vid in c:
            if vid not in used:
                chosen = (vc, dur, title, vid)
                break
        if chosen:
            vc, dur, title, vid = chosen
            used.add(vid)
            plan[name] = vid
            print(f"{name}: {title[:60]} | {vc:,} views | {dur//60}m{dur%60}s | {vid}")
        else:
            print(f"{name}: NO CANDIDATE FOUND for '{q}'")
    with open("tools/plan.json", "w") as f:
        json.dump(plan, f)
