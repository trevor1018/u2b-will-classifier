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
    # 女子露營失蹤案 — LLM hallucinated 肯塔基州. The case's only geographic
    # anchor is Nutty Putty Cave (堅果油灰洞), which is in Utah County, Utah —
    # not Kentucky. Corrected to Utah state (centroid), consistent with the
    # state-level pins the LLM used elsewhere.
    "tDOeZnQkg3E": {
        "lat": 39.321,
        "lon": -111.094,
        "city": "猶他州",
        "country": "美國",
        "note": "fix hallucinated 肯塔基州 → 猶他州 (Nutty Putty Cave is in Utah)",
    },
    # 空姐離奇失蹤案 = Helle Crafts (Pan Am), 1986 woodchipper murder, Dr.
    # Henry Lee case. State-level 康乃狄克州 was correct; refined to the actual
    # town, Newtown, CT.
    "cTVWfoHGT7M": {
        "lat": 41.4137,
        "lon": -73.3037,
        "city": "紐敦 (Newtown, CT)",
        "country": "美國",
        "note": "refine 康乃狄克州 → Newtown, CT (Helle Crafts case)",
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
