"""Quick inspector — shows what's in the 'other' bucket and lists unique
countries (with their case counts) so we can spot duplicates."""
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
d = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))

print("=== 案件類型分布 ===")
for k, n in Counter(c["caseType"] for c in d["cases"]).most_common():
    print(f"  {k}: {n}")
print()
print("=== 'other' 類別 (n=%d) ===" % sum(1 for c in d["cases"] if c["caseType"] == "other"))
for c in d["cases"]:
    if c["caseType"] != "other":
        continue
    print(f"  caseName={c['caseName']!r}")
    print(f"    title={c['title'][:80]!r}")

print("\n=== 國家分布 (unique=%d) ===" % len(set(c.get("country") or "?" for c in d["cases"])))
for k, n in Counter(c.get("country") or "?" for c in d["cases"]).most_common():
    # Print with quotes so we can see exactly what string is stored
    print(f"  {n:4d}  {k!r}")
