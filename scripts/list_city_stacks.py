"""Find points where multiple cases sit on identical (or near-identical)
lat/lon — typically city centres the LLM emitted as a generic placeholder
when it didn't know the specific district / address.
"""
import json, sys
from collections import defaultdict
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from country_centroids import COUNTRY_CENTROIDS

ROOT = Path(__file__).resolve().parent.parent
cases = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))["cases"]

groups = defaultdict(list)
for c in cases:
    if c["lat"] is None or c["lon"] is None:
        continue
    # 0.01° ≈ 1km bucket
    key = (round(c["lat"], 2), round(c["lon"], 2))
    groups[key].append(c)

# Filter to groups with > 1 case, exclude country centroids (those are a
# separate bucket the user already saw).
country_centroid_keys = {
    (round(v[0], 2), round(v[1], 2))
    for v in COUNTRY_CENTROIDS.values()
    if v is not None
}

multi_groups = sorted(
    [(k, v) for k, v in groups.items() if len(v) > 1 and k not in country_centroid_keys],
    key=lambda x: -len(x[1]),
)

print(f"=== {len(multi_groups)} 個城市點疊了 >1 案件，總共 {sum(len(v) for _, v in multi_groups)} 件 ===\n")
for (lat, lon), cs in multi_groups:
    sample = cs[0]
    label = f"{sample.get('country') or '?'} / {sample.get('city') or '?'}"
    print(f"{label}  ({lat}, {lon})  — {len(cs)} 件")
    for c in cs:
        cyear = c.get("crimeYear") or "?"
        print(f"  • [{cyear}] {c['caseName']}")
    print()
