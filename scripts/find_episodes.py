"""Multi-part episode consistency audit.

Many cases are split into 上/下 (or 上集/下集, 前篇/後篇 …) episodes that must
share the same location, crime year and type. This script finds every
episode-marked case, groups the parts of the same case together, and flags any
group whose parts disagree on country / coordinates.

Grouping key is derived from `caseName`:
  - "貝恩家庭滅門案（上）" / "（下）"      → 貝恩家庭滅門案
  - "…（馬德琳·麥肯案 下集）"              → 馬德琳·麥肯案  (embedded series name)
  - "普克卡瓦血屋案" (no marker in name)   → 普克卡瓦血屋案 (still grouped by title marker)

Read-only — reports; it does not edit anything. Apply fixes via manual_pins.py.

Run:
    python scripts/find_episodes.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "frontend/public/data/cases.json").read_text(encoding="utf-8"))["cases"]

EP = r"(上集|下集|上篇|下篇|前篇|後篇|完結篇|第[一二三四五]集|[上下])"
# A title carries an episode marker if any of these appear.
TITLE_MARK = re.compile(r"[（(]" + EP + r"[)）]|上集|下集|前篇|後篇|完結篇")
# Embedded named series inside parens, e.g. （馬德琳·麥肯案 下集）
EMBEDDED = re.compile(r"[（(]\s*([^（）()]+?)\s*" + EP + r"\s*[)）]")
# Standalone marker to strip, e.g. 貝恩家庭滅門案（上）
STANDALONE = re.compile(r"[（(]\s*" + EP + r"\s*[)）]")


def group_key(case_name: str, title: str) -> str:
    name = case_name or title or ""
    m = EMBEDDED.search(name)
    if m and len(m.group(1).strip()) >= 3:
        return m.group(1).strip()
    k = STANDALONE.sub("", name)
    return k.strip("，,：: 　")


groups: dict[str, list[dict]] = defaultdict(list)
for c in CASES:
    title = c.get("title", "")
    if not TITLE_MARK.search(title):
        continue
    groups[group_key(c.get("caseName", ""), title)].append(c)

multi = {k: v for k, v in groups.items() if len(v) >= 2}

print(f"=== {len(multi)} multi-part cases ({sum(len(v) for v in multi.values())} episodes) ===\n")

# Coord tolerance for "same place": episodes geocoded to the same city can
# land a few km apart. 0.3° (~33 km) tolerates that while still catching parts
# pinned to genuinely different locales.
COORD_TOL = 0.3

inconsistent = 0
for key, parts in sorted(multi.items()):
    countries = {p.get("country") for p in parts}
    lats = [p["lat"] for p in parts]
    lons = [p["lon"] for p in parts]
    spread = max(max(lats) - min(lats), max(lons) - min(lons))
    ok = len(countries) == 1 and spread <= COORD_TOL
    if not ok:
        inconsistent += 1
    mark = "OK " if ok else "✗ MISMATCH"
    print(f"[{mark}] {key}")
    for p in parts:
        print(f"    {p.get('id')}  {p.get('country')}/{p.get('city')}  "
              f"({p['lat']:.4f}, {p['lon']:.4f})  crimeYear={p.get('crimeYear')}")
        print(f"        {p.get('title', '')[:55]}")
    print()

if inconsistent:
    print(f"⚠ {inconsistent} case(s) have parts in different places — fix via manual_pins.py")
else:
    print("All multi-part cases are internally consistent.")
