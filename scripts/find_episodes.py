"""Multi-part episode grouping + consistency audit.

Many cases are split into 上/下 (or 上集/下集, 前篇/後篇 …) episodes that must
share the same location, crime year and type. This module provides the shared
grouping logic (also imported by refresh.py to stamp episodeGroup/episodeLabel
onto cases.json) and, when run directly, a consistency audit that flags any
group whose parts sit in a different country or far apart.

Grouping key is derived from `caseName`:
  - "貝恩家庭滅門案（上）" / "（下）"      → 貝恩家庭滅門案
  - "…（馬德琳·麥肯案 下集）"              → 馬德琳·麥肯案  (embedded series name)
  - "普克卡瓦血屋案" (no marker in name)   → 普克卡瓦血屋案 (grouped by title marker)

Run:
    python scripts/find_episodes.py
"""
from __future__ import annotations

import re

EP = r"(上集|中集|下集|上篇|中篇|下篇|前篇|後篇|完結篇|第[一二三四五]集|[上中下])"
# A title carries an episode marker if any of these appear.
TITLE_MARK = re.compile(r"[（(]" + EP + r"[)）]|上集|下集|前篇|後篇|完結篇")
# Embedded named series inside parens, e.g. （馬德琳·麥肯案 下集）
_EMBEDDED = re.compile(r"[（(]\s*([^（）()]+?)\s*" + EP + r"\s*[)）]")
# Standalone marker to strip, e.g. 貝恩家庭滅門案（上）
_STANDALONE = re.compile(r"[（(]\s*" + EP + r"\s*[)）]")

_ZH_NUM = "一二三四五"


def has_marker(title: str) -> bool:
    return bool(TITLE_MARK.search(title or ""))


def group_key(case_name: str, title: str) -> str:
    """Stable key that collapses the episodes of one case together."""
    name = case_name or title or ""
    m = _EMBEDDED.search(name)
    if m and len(m.group(1).strip()) >= 3:
        return m.group(1).strip()
    k = _STANDALONE.sub("", name)
    return k.strip("，,：: 　")


def episode_meta(title: str, case_name: str) -> tuple[str | None, int]:
    """Return (label, order) for an episode, e.g. ("上集", 0) / ("下集", 1)."""
    t = f"{title} {case_name}"
    m = re.search(r"第([一二三四五])集", t)
    if m:
        return (f"第{m.group(1)}集", _ZH_NUM.index(m.group(1)))
    if re.search(r"後篇|完結篇|下集|[（(]下[)）]", t):
        return ("下集", 2)
    if re.search(r"中篇|中集|[（(]中[)）]", t):
        return ("中集", 1)
    if re.search(r"前篇|上集|[（(]上[)）]", t):
        return ("上集", 0)
    return (None, 0)


def annotate_episodes(cases: list[dict]) -> int:
    """Stamp episodeGroup / episodeLabel / episodeIndex onto every case that
    belongs to a 2+-part group. Mutates `cases` in place; returns #cases
    annotated."""
    from collections import defaultdict

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        if has_marker(c.get("title", "")):
            groups[group_key(c.get("caseName", ""), c.get("title", ""))].append(c)

    annotated = 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        for c in members:
            label, order = episode_meta(c.get("title", ""), c.get("caseName", ""))
            c["episodeGroup"] = key
            c["episodeLabel"] = label or "?"
            c["episodeIndex"] = order
            annotated += 1
    return annotated


def _main() -> None:
    import json
    import sys
    from collections import defaultdict
    from pathlib import Path

    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parent.parent
    cases = json.loads((root / "frontend/public/data/cases.json").read_text(encoding="utf-8"))["cases"]

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        if has_marker(c.get("title", "")):
            groups[group_key(c.get("caseName", ""), c.get("title", ""))].append(c)
    multi = {k: v for k, v in groups.items() if len(v) >= 2}

    print(f"=== {len(multi)} multi-part cases ({sum(len(v) for v in multi.values())} episodes) ===\n")

    # Coord tolerance for "same place": episodes geocoded to the same city can
    # land a few km apart. 0.3° (~33 km) tolerates that while still catching
    # parts pinned to genuinely different locales.
    coord_tol = 0.3
    inconsistent = 0
    for key, parts in sorted(multi.items()):
        countries = {p.get("country") for p in parts}
        lats = [p["lat"] for p in parts]
        lons = [p["lon"] for p in parts]
        spread = max(max(lats) - min(lats), max(lons) - min(lons))
        ok = len(countries) == 1 and spread <= coord_tol
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


if __name__ == "__main__":
    _main()
