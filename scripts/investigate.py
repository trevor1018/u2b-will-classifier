"""Investigate specific issues:
1. Is 2022 梨泰院踩踏事件 (id 2Dk2c1t4Rt4) actually in the data?
2. What's its lat/lon?
3. Are the 2 梨泰院 cases really at the exact same point?
"""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

cases = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))["cases"]

target_id = "2Dk2c1t4Rt4"
match = [c for c in cases if c["id"] == target_id]
print(f"=== Looking for video id {target_id} ===")
if match:
    c = match[0]
    print(f"Found: {c['caseName']}")
    print(f"  title: {c['title']}")
    print(f"  country: {c['country']}, city: {c['city']}")
    print(f"  lat: {c['lat']}, lon: {c['lon']}")
else:
    print("NOT in data!")

print()
print("=== All 梨泰院/Itaewon cases ===")
for c in cases:
    if "梨泰院" in c["caseName"] or "梨泰院" in c["title"] or "Itaewon" in c["title"]:
        print(f"  id={c['id']}  caseName={c['caseName']!r}")
        print(f"    lat={c['lat']}  lon={c['lon']}  city={c['city']!r}")
        print(f"    title: {c['title'][:80]}")

print()
print("=== All 辛普森 cases ===")
for c in cases:
    if "辛普森" in c["caseName"] or "辛普森" in c["title"]:
        print(f"  id={c['id']}  caseName={c['caseName']!r}")
        print(f"    lat={c['lat']}  lon={c['lon']}  city={c['city']!r}")
        print(f"    title: {c['title'][:80]}")
