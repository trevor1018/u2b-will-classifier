"""List cases that still don't have a specific lat/lon — split by reason."""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from country_centroids import COUNTRY_CENTROIDS

ROOT = Path(__file__).resolve().parent.parent
cases = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))["cases"]
cache = json.load(open(ROOT / "scripts/.cache/classifications.json", encoding="utf-8"))


def at_centroid(c):
    if c["lat"] is None or c["lon"] is None:
        return False
    cc = COUNTRY_CENTROIDS.get(c.get("country") or "")
    if not cc:
        return False
    return abs(c["lat"] - cc[0]) < 0.001 and abs(c["lon"] - cc[1]) < 0.001


centroid_cases = [c for c in cases if at_centroid(c)]
no_geo_cases = [c for c in cases if c["lat"] is None or c["lon"] is None]

print(f"=== 落在國家中心點 ({len(centroid_cases)} 件) ===")
print("(LLM 知道國家但無法判斷具體城市，目前疊在國家中心)\n")
for c in centroid_cases:
    cl = cache.get(c["id"], {})
    print(f"  • {c['caseName']}")
    print(f"    國家={c['country']!r}  cache.city={cl.get('city')!r}")
    print(f"    title: {c['title'][:90]}")
    print(f"    https://youtu.be/{c['id']}")
    print()

print(f"\n=== 完全無座標 ({len(no_geo_cases)} 件) ===")
print("(LLM 與 web_search 都找不到具體地點)\n")
for c in no_geo_cases:
    cl = cache.get(c["id"], {})
    print(f"  • {c['caseName']}")
    print(f"    cache: country={cl.get('country')!r} city={cl.get('city')!r}")
    print(f"    title: {c['title'][:90]}")
    print(f"    https://youtu.be/{c['id']}")
    print()
