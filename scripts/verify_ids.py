"""Print the first N video IDs and case names so we can spot ID corruption."""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
d = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))
print(f"total cases: {len(d['cases'])}")
print(f"source: {d['source']}")
print(f"sample IDs:")
for c in d["cases"][:8]:
    vid = c["id"]
    print(f"  {vid}  ({len(vid)} chars)  ->  https://youtu.be/{vid}  -- {c['caseName']}")
print("---")
# Sanity: any IDs that look fake (wrong length / chars)?
import re
bad = [c for c in d["cases"] if not re.match(r"^[A-Za-z0-9_-]{11}$", c["id"])]
print(f"IDs not matching standard 11-char yt id: {len(bad)}")
for c in bad[:5]:
    print(f"  bad: {c['id']!r}")
