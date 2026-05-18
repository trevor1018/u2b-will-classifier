"""Audit which cases lack crimeYear / resolveYear so we can target manual
fixes. Splits into three buckets:

  1. Missing crimeYear entirely (the most painful gap — case has no date
     anywhere)
  2. Has crimeYear but status=solved without a resolveYear (logical gap —
     a solved case should know when it closed)
  3. Has crimeYear but no resolveYear, not solved (cold / ongoing /
     unknown — null resolveYear is legitimate, NOT flagged)
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
d = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))
cases = d["cases"]

missing_crime = []
solved_no_resolve = []

# A re-scan of title/description for a 4-digit year would catch
# the obvious "missed extractions" (LLM had a year visible but didn't pick
# it up). Helps the user prioritise.
import re
YEAR_PAT = re.compile(r"(?:19[5-9]\d|20[0-2]\d)")  # 1950-2029

for c in cases:
    cy = c.get("crimeYear")
    ry = c.get("resolveYear")
    status = c.get("status")

    if cy is None:
        # Did the title secretly contain a year we could grab without LLM?
        m = YEAR_PAT.search(c.get("title", ""))
        c["_year_hint_in_title"] = m.group(0) if m else None
        missing_crime.append(c)
    elif status == "solved" and ry is None:
        solved_no_resolve.append(c)

# Sort by published date descending — newer videos first since you've
# probably already forgotten older ones
def pub_key(c):
    return c.get("publishedAt", "")

missing_crime.sort(key=pub_key, reverse=True)
solved_no_resolve.sort(key=pub_key, reverse=True)

OUT_FILE = ROOT / "scripts" / "missing_dates.txt"
_buf: list[str] = []
_real_print = print
def print(*args, **kwargs):  # type: ignore[no-redef]
    s = " ".join(str(a) for a in args)
    _buf.append(s)
    _real_print(s, **kwargs)

print(f"Total cases: {len(cases)}")
print(f"  no crimeYear:              {len(missing_crime)}")
print(f"  solved but no resolveYear: {len(solved_no_resolve)}")
print()

# Country distribution of the no-crimeYear set
from collections import Counter
print("=== no-crimeYear by country (top 12) ===")
ctry_counts = Counter((c.get("country") or "?") for c in missing_crime)
for k, v in ctry_counts.most_common(12):
    print(f"  {v:3d}  {k}")
print()

# Pre-scan: cases where the title contains a 4-digit year — these are
# "low-hanging fruit", LLM just missed the obvious clue.
in_title = [c for c in missing_crime if c.get("_year_hint_in_title")]
print(f"=== quick wins: title contains a year ({len(in_title)} 件) ===")
print("These could be batch-fixed by a regex pass over titles.\n")
for c in in_title[:30]:
    year = c["_year_hint_in_title"]
    print(f"  {year}  {c['id']}  {c['title'][:80]}")
print(f"  ... ({len(in_title) - 30} more)" if len(in_title) > 30 else "")
print()

print(f"=== Missing crimeYear ({len(missing_crime)} 件) ===\n")
for c in missing_crime:
    member = "🔒" if c.get("memberOnly") else "  "
    pub = c.get("publishedAt", "")[:10]
    country = c.get("country") or "?"
    city = c.get("city") or "?"
    print(f"{member} [{pub}] {c['id']}  ({country} / {city})")
    print(f"   {c['title'][:90]}")
    print(f"   https://youtu.be/{c['id']}")
    print()

print(f"\n=== Solved but no resolveYear ({len(solved_no_resolve)} 件) ===\n")
for c in solved_no_resolve:
    member = "🔒" if c.get("memberOnly") else "  "
    pub = c.get("publishedAt", "")[:10]
    cy = c.get("crimeYear")
    country = c.get("country") or "?"
    print(f"{member} [{pub}] {c['id']}  crime={cy}  ({country})")
    print(f"   {c['title'][:90]}")
    print(f"   https://youtu.be/{c['id']}")
    print()

OUT_FILE.write_text("\n".join(_buf), encoding="utf-8")
