"""Audit how many cases use country-centroid fallback vs LLM-given coords,
and how many of those have a city string we could geocode."""
import json, sys
from collections import Counter
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from country_centroids import COUNTRY_CENTROIDS

cases = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))["cases"]
cache = json.load(open(ROOT / "scripts/.cache/classifications.json", encoding="utf-8"))

# A case landed on a country centroid if its lat/lon ≈ the COUNTRY_CENTROIDS entry
def at_centroid(c):
    if c["lat"] is None or c["lon"] is None:
        return False
    cc = COUNTRY_CENTROIDS.get(c.get("country") or "")
    if not cc:
        return False
    return abs(c["lat"] - cc[0]) < 0.001 and abs(c["lon"] - cc[1]) < 0.001

bucket_centroid = []
bucket_real = []
bucket_no_geo = []
for c in cases:
    if c["lat"] is None or c["lon"] is None:
        bucket_no_geo.append(c)
    elif at_centroid(c):
        bucket_centroid.append(c)
    else:
        bucket_real.append(c)

print(f"Total cases: {len(cases)}")
print(f"  LLM-given specific coords: {len(bucket_real)}")
print(f"  Country-centroid fallback: {len(bucket_centroid)}")
print(f"  No coords at all:          {len(bucket_no_geo)}")

print(f"\n=== centroid-fallback cases — what does the LLM cache hold? ===")
have_city = 0
no_city_no_coord_in_cache = 0
for c in bucket_centroid:
    cl = cache.get(c["id"], {})
    has_city = bool(cl.get("city"))
    has_llm_coord = cl.get("lat") is not None and cl.get("lon") is not None
    if has_city and not has_llm_coord:
        have_city += 1
    if not has_city and not has_llm_coord:
        no_city_no_coord_in_cache += 1

print(f"  centroid cases with city string but no LLM coords: {have_city}")
print(f"    (these we can geocode ourselves — Nominatim or LLM lookup)")
print(f"  centroid cases with neither city nor LLM coords: {no_city_no_coord_in_cache}")

# Show top 10 stacked centroid points
print(f"\n=== centroid-fallback grouped by country ===")
for k, n in Counter(c["country"] for c in bucket_centroid).most_common(10):
    print(f"  {k}: {n} cases stacked on centroid")

# Sample of (centroid, has city in cache)
print(f"\n=== sample centroid cases ===")
for c in bucket_centroid[:8]:
    cl = cache.get(c["id"], {})
    print(f"  {c['caseName']!r:40s} country={c['country']!r:8s} cache.city={cl.get('city')!r:15s} cache.lat={cl.get('lat')}")
