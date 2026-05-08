"""Sample ~10 videos and check whether any have CC."""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

import yt_dlp

raw = json.load(open(ROOT / "scripts/.cache/raw_videos.json", encoding="utf-8"))
sample_ids = [v["id"] for v in raw[:15]]

opts = {"quiet": True, "no_warnings": True, "skip_download": True}
have_auto = 0
have_manual = 0
total = 0

with yt_dlp.YoutubeDL(opts) as ydl:
    for vid in sample_ids:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        except Exception as e:
            print(f"  {vid}: error {e}")
            continue
        total += 1
        auto = info.get("automatic_captions") or {}
        manual = info.get("subtitles") or {}
        a = sorted(auto.keys())[:5]
        m = sorted(manual.keys())[:5]
        print(f"  {vid}: auto={a}  manual={m}")
        if auto:
            have_auto += 1
        if manual:
            have_manual += 1

print(f"\n{total} videos sampled. auto-cc: {have_auto}, manual-cc: {have_manual}")
