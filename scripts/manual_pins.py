"""Manual coordinate fixes — for cases that LLM/web_search can't pin and
the user has provided ground truth."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "scripts/.cache/classifications.json"

# (video_id) -> (lat, lon, city, country, note)
PINS = {
    # Compilation about 3 cruise overboard stories. User suggested marking
    # at midpoint of one route's central ocean. Using route 1 (Miami →
    # Jamaica) midpoint, in the Caribbean — most representative of cruise
    # overboard incidents (2/3 routes are Caribbean-area).
    "OUmFmt9X9rc": {
        "lat": 21.87,
        "lon": -78.49,
        "city": "加勒比海 (郵輪墜海合集)",
        "country": "海上",
        "note": "compilation — Miami/Jamaica route midpoint",
    },
}


def main():
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    for vid, pin in PINS.items():
        cache.setdefault(vid, {})
        cache[vid]["lat"] = pin["lat"]
        cache[vid]["lon"] = pin["lon"]
        cache[vid]["city"] = pin["city"]
        cache[vid]["country"] = pin["country"]
        print(f"  pinned {vid}: {pin['note']}  ->  ({pin['lat']}, {pin['lon']})")
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"updated {len(PINS)} cache entries")


if __name__ == "__main__":
    main()
