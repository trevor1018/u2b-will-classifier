"""Undo any Nominatim placements that were given non-city strings (e.g.
'大西洋' got mapped to Osaka). Walks the cache and clears lat/lon for
any entry whose city is in our blacklist.
"""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh import is_geocodable_city, NON_CITY_KEYWORDS, UNKNOWN_CITY

ROOT = Path(__file__).resolve().parent.parent
cache_path = ROOT / "scripts/.cache/classifications.json"
cache = json.loads(cache_path.read_text(encoding="utf-8"))
fixed = 0
for vid, cl in cache.items():
    city = cl.get("city")
    if cl.get("lat") is None or cl.get("lon") is None:
        continue
    if not city:
        continue
    if not is_geocodable_city(city):
        print(f"reverting {vid}: city={city!r} (non-geocodable)")
        cl["lat"] = None
        cl["lon"] = None
        fixed += 1
cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"reverted {fixed} entries")
