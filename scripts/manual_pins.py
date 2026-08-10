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
    # 普克卡瓦血屋案（上）— the （上）episode was pinned to Finland while the
    # （下）episode sat in New Zealand. Pukekawa is in Waikato, NZ (the Crewe
    # murders). Aligned to the （下）episode's NZ coords.
    "QPWmMHorrcc": {
        "lat": -37.8,
        "lon": 174.9,
        "city": "普克卡瓦",
        "country": "紐西蘭",
        "note": "fix 芬蘭 → 紐西蘭; match （下）episode qTPxc7JdSVA",
    },
    # 矽谷精英一家冰封禁區案 = the James Kim family, Nov 2006. The San
    # Francisco family got stranded on a side road off Bear Camp Road in the
    # Rogue River Canyon (Siskiyou National Forest), SW Oregon — NOT California
    # (the LLM guessed 加州 from "Silicon Valley family"). James Kim died of
    # exposure in the Klamath Mountains while seeking help.
    "0as9lkl6cHw": {
        "lat": 42.66,
        "lon": -123.93,
        "city": "奧勒岡州 (Bear Camp Road, 羅格河峽谷)",
        "country": "美國",
        "note": "fix 加州 → 奧勒岡州 (James Kim family, 2006)",
    },
    # 黑寡婦筧千佐子 (Chisako Kakehi). Refine 關西地區 → Muko City, Kyoto
    # Prefecture: her 4th husband died there, she was arrested there, and the
    # Kyoto District Court sentenced her (2017).
    "gi2NvbCke3Q": {
        "lat": 34.9486,
        "lon": 135.6996,
        "city": "京都府向日市 (Muko)",
        "country": "日本",
        "note": "refine 關西地區 → 京都府向日市 (Chisako Kakehi case)",
    },
    # 彭楚盈白骨案 (1999). Refine 香港 → Yau Ma Tei: the model's skeletal
    # remains were found in a unit at 華德大廈 (Wah Tak Building), Yau Ma Tei,
    # opposite the fruit market.
    "f6dY8aq2ra0": {
        "lat": 22.311,
        "lon": 114.170,
        "city": "香港油麻地 (華德大廈)",
        "country": "中國",
        "note": "refine 香港 → 油麻地 (彭楚盈白骨案, remains found at 華德大廈)",
    },
    # 普克卡瓦血屋案（中）— a new middle episode that came in via a weekly
    # refresh with the same Finland geo bug as the （上）once had, and no year.
    # Pukekawa is in Waikato, NZ (the 1970 Crewe murders); aligned to the
    # （上）/（下）episodes' coords + crimeYear so all three are consistent.
    "E8R85Gtwwj0": {
        "lat": -37.8,
        "lon": 174.9,
        "city": "普克卡瓦",
        "country": "紐西蘭",
        "crimeYear": 1970,
        "note": "fix 芬蘭 → 紐西蘭 + crimeYear 1970; match （上）/（下）episodes",
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
        # Optional ground-truth year overrides.
        for yk in ("crimeYear", "resolveYear"):
            if yk in pin:
                cache[vid][yk] = pin[yk]
        print(f"  pinned {vid}: {pin['note']}  ->  ({pin['lat']}, {pin['lon']})")
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"updated {len(PINS)} cache entries")


if __name__ == "__main__":
    main()
