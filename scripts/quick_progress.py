"""Quick progress probe for any in-flight web_search run."""
import json, os, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

cache_path = ROOT / "scripts/.cache/classifications.json"
print(f"cache size: {cache_path.stat().st_size:,} bytes")
print(f"cache mtime: {os.path.getmtime(cache_path):.0f} (epoch)")

cache = json.loads(cache_path.read_text(encoding="utf-8"))
have_geo = sum(1 for c in cache.values() if c.get("lat") is not None)
print(f"entries with lat/lon: {have_geo}/{len(cache)}")

# Count entries that are eligible for web_search target (no lat/lon AND city is missing/unknown)
UNKNOWN = {"不明", "未知", "未明", "?", "未提及", "未明確指出", "未明確"}
eligible = 0
for c in cache.values():
    if c.get("lat") is not None:
        continue
    city = c.get("city")
    if not city or city in UNKNOWN:
        eligible += 1
print(f"still eligible for web_search: {eligible}")
