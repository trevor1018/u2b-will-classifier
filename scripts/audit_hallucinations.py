"""Quality audit — flag cases where the LLM likely *invented* a specific
location, while NOT flagging cases where it correctly inferred a famous
case's location from world knowledge.

The v1 heuristic flagged any case whose assigned country/city keyword was
absent from the title + short description. That over-fired badly: famous
cases (辛普森案 → Brentwood, 泰坦號 → Newfoundland, 愛達荷大學謀殺案 →
Moscow, Idaho) have well-known locations the LLM knew from world knowledge
but that never appear literally in the title/description.

v2 adds a discriminator on top of the v1 "no place keyword" filter:

    GENERIC-TOKEN SUBTRACTION
    Strip every generic descriptor token (role words 女子/男童/空姐,
    event words 失蹤/遇害/救援, suffixes 案/事件 …) from the case name.
      - residual meaningful text remains  → a proper-noun ANCHOR exists
        (person / institution / landmark / ship) → the LLM could legitimately
        know the location → NOT a hallucination → suppressed.
      - nothing meaningful remains        → the name is purely generic, the
        LLM had nothing to anchor a specific place to → SUSPICIOUS → kept.

Suspicious cases are ranked by location granularity (street/district worse
than country) then description length (shorter = more suspicious).

No LLM calls — pure heuristic, costs nothing.

Run:
    python scripts/audit_hallucinations.py              # show suspicious
    python scripts/audit_hallucinations.py --suppressed # also show what was
                                                        # filtered as world-knowledge
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SHOW_SUPPRESSED = "--suppressed" in sys.argv

ROOT = Path(__file__).resolve().parent.parent
CACHE = json.loads((ROOT / "scripts/.cache/classifications.json").read_text(encoding="utf-8"))
RAW = json.loads((ROOT / "scripts/.cache/raw_videos.json").read_text(encoding="utf-8"))
RAW_BY_ID = {v["id"]: v for v in RAW}

# Strip footers / boilerplate the description often opens with so the
# "description short" check measures actual case content.
BOILERPLATE = re.compile(
    r"會員影片列表[:：]?\s*https?://\S+\s*"
    r"|會員專享影片[:：]?\s*https?://\S+\s*",
)

# Split a place string into searchable 2+ char tokens.
SPLIT_PAT = re.compile(r"[、，,/()（）\s\-–—]+")


def place_tokens(country: str | None, city: str | None) -> set[str]:
    out: set[str] = set()
    for s in (country or "", city or ""):
        s = s.strip()
        if not s or s in ("不明", "未知", "未明", "海上"):
            continue
        out.add(s)
        for part in SPLIT_PAT.split(s):
            part = part.strip()
            if len(part) >= 2:
                out.add(part)
        for suffix in ("市", "縣", "區", "省", "州", "府"):
            for whole in list(out):
                if whole.endswith(suffix) and len(whole) > 2:
                    out.add(whole[:-1])
    return out


# --------------------------------------------------------------------------
# Generic-token subtraction: what's left after removing descriptor words is a
# proper-noun anchor (person / place / institution the LLM could look up).
# --------------------------------------------------------------------------

# Multi-char generic phrases stripped first (longest-match wins), then single
# generic chars. Built from scanning the actual flagged case names — extend
# freely; the "residual" column in the output shows what each rule leaves.
GENERIC_PHRASES = [
    # roles / people (descriptive, not named)
    "高中女子", "女大學生", "大學生", "女學生", "小學生", "中學生",
    "啦啦隊長", "啦啦隊", "空姐", "女船員", "船員", "男童", "女童", "男孩",
    "女孩", "少女", "少年", "女子", "男子", "女生", "男生", "婦人", "夫婦",
    "母子", "母女", "父子", "父女", "一家", "全家", "家庭", "新郎", "新娘",
    "妻子", "丈夫", "女店主", "店主", "女店員", "店員", "女演員", "演員",
    "富翁", "億萬富翁", "商人", "老人", "老翁", "老婦", "青年", "情侶",
    # event / crime words
    "無差別殺人", "隨機殺人", "連環殺人", "連續殺人", "滅門", "謀殺",
    "殺害", "遇害", "命案", "兇殺", "被害", "遭遇不測", "遇襲", "暗算",
    "失蹤", "離奇失蹤", "神秘失蹤", "墜井", "墜海", "墜崖", "沉沒",
    "越獄", "綁架", "劫持", "劫案", "搶劫", "詐騙", "偽造", "偽畫",
    "冤獄", "中毒", "火災", "越野", "救援", "求生", "探險", "迷航",
    "迷途", "失事", "事故", "遊輪", "郵輪", "帆船", "潛艇", "潛水",
    "登山", "露營", "尋寶", "偷渡",
    # place-type / generic nouns
    "臥室", "公寓", "宿舍", "旅館", "酒店", "飯店", "民宅", "住宅",
    "玉米地", "煙火晚會", "晚會", "深夜", "放學後", "後院", "井道",
    "懸崖", "洞穴", "藍洞", "潟湖", "礦", "隧道",
    # misc descriptors
    "離奇", "神秘", "神祕", "詭異", "驚魂", "謎案", "懸案", "疑案",
    "奇案", "血案", "慘案", "舊案", "積案", "集", "合集", "系列",
]
GENERIC_CHARS = set("案件事故謎男女的了在與和及之號歲天年月日夜")


def residual_anchor(name: str) -> str:
    """Return the proper-noun residue of a case name after removing generic
    descriptor tokens. Empty string == purely generic (suspicious)."""
    s = name or ""
    # A middle dot is an unmistakable transliterated-person-name marker.
    # Keep it as an anchor immediately.
    if "·" in s or "・" in s:
        return s
    for phrase in sorted(GENERIC_PHRASES, key=len, reverse=True):
        s = s.replace(phrase, "")
    s = "".join(ch for ch in s if ch not in GENERIC_CHARS)
    # drop digits / ascii / punctuation left behind
    s = re.sub(r"[0-9A-Za-z\s、，,/()（）\-–—:：&]+", "", s)
    return s.strip()


# Landmark / institution / named-vehicle keywords that, if present, mean the
# case is anchorable even when residual subtraction is imperfect.
ANCHOR_KEYWORDS = (
    "大學", "大学", "學院", "学院", "監獄", "看守所", "莊園", "莊", "大樓",
    "旅社", "塔", "宮", "殿", "島", "寺", "城", "礦", "號", "艦", "郵輪",
    "遊輪", "潛艇", "銀行", "百貨", "車站", "機場", "大橋",
)

# Location-granularity scoring: finer detail = a bolder (riskier) claim.
FINE_MARKERS = ("丁目", "交叉口", "路", "街", "巷", "町", "洞", "村", "鄉", "區")
MID_MARKERS = ("市", "縣", "郡")
COARSE_MARKERS = ("州", "省", "府")


def granularity(city: str | None) -> tuple[int, str]:
    c = city or ""
    if any(m in c for m in FINE_MARKERS):
        return 3, "street/district"
    if any(m in c for m in MID_MARKERS):
        return 2, "city"
    if any(m in c for m in COARSE_MARKERS):
        return 1, "state/province"
    return 0, "country-only"


suspicious: list[dict] = []
suppressed: list[dict] = []

for vid, cl in CACHE.items():
    if cl.get("lat") is None or cl.get("lon") is None:
        continue
    country = cl.get("country")
    city = cl.get("city")
    if not country and not city:
        continue
    if country in ("不明", None, ""):
        continue

    v = RAW_BY_ID.get(vid)
    if not v:
        continue
    sn = v.get("snippet", {})
    title = sn.get("title", "")
    desc_raw = sn.get("description", "") or ""
    desc_clean = BOILERPLATE.sub("", desc_raw).strip()
    haystack = (title + " " + desc_clean[:400]).lower()

    tokens = place_tokens(country, city)
    if not tokens:
        continue

    # v1 filter: place keyword must be absent from title + short description.
    if any(tok.lower() in haystack for tok in tokens):
        continue
    if len(desc_clean) > 300:
        continue

    # v2 discriminator: does the case name carry a proper-noun anchor?
    name = cl.get("caseName") or ""
    anchor = residual_anchor(name)
    has_kw = any(k in name for k in ANCHOR_KEYWORDS)
    gscore, glabel = granularity(city)

    rec = {
        "id": vid,
        "caseName": name,
        "title": title,
        "country": country,
        "city": city,
        "lat": cl["lat"],
        "lon": cl["lon"],
        "desc_len": len(desc_clean),
        "residual": anchor,
        "anchor_kw": has_kw,
        "granularity": glabel,
        "gscore": gscore,
    }

    if anchor or has_kw:
        suppressed.append(rec)
    else:
        suspicious.append(rec)

# Most suspicious first: bolder location claim, then shorter description.
suspicious.sort(key=lambda f: (-f["gscore"], f["desc_len"]))

total_flagged = len(suspicious) + len(suppressed)
print(f"=== v1 would flag {total_flagged}; v2 keeps {len(suspicious)} suspicious, "
      f"suppresses {len(suppressed)} as world-knowledge ===\n")
print("SUSPICIOUS — generic case name, no proper-noun anchor, precise location,")
print("no place keyword in title/description. These are the real hallucination")
print("candidates, most-suspicious first.\n")

for i, f in enumerate(suspicious, 1):
    print(f"[{i}/{len(suspicious)}]  {f['id']}  ({f['granularity']}, desc {f['desc_len']} chars)")
    print(f"  title:    {f['title']}")
    print(f"  caseName: {f['caseName']}")
    print(f"  assigned: {f['country']} / {f['city']}  ({f['lat']:.4f}, {f['lon']:.4f})")
    print(f"  https://youtu.be/{f['id']}")
    print()

if SHOW_SUPPRESSED:
    print(f"\n=== {len(suppressed)} SUPPRESSED (has anchor → probably correct) ===\n")
    for f in suppressed:
        why = f["residual"] or ("keyword:" + next(k for k in ANCHOR_KEYWORDS if k in f["caseName"]))
        print(f"  {f['id']}  {f['caseName']}  →  {f['country']}/{f['city']}")
        print(f"      anchor: {why!r}")

# Write suspicious IDs so a follow-up script can act on them.
out_path = ROOT / "scripts" / "flagged_hallucinations.txt"
out_path.write_text(
    "\n".join(f"{f['id']}\t{f['caseName']}\t{f['country']}/{f['city']}\t{f['granularity']}"
              for f in suspicious),
    encoding="utf-8",
)
print(f"\nSuspicious list written → {out_path}  ({len(suspicious)} ids)")
