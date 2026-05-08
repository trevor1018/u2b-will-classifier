"""List unique countries with case counts, sorted, so we can spot duplicates."""
import json, sys
from collections import Counter
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
d = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))

c = Counter(x.get("country") or "(null)" for x in d["cases"])
print(f"=== {len(c)} unique countries ===\n")
for name, n in c.most_common():
    # Print with quotes so we see exact byte content
    print(f"  {n:4d}  {name!r}")
